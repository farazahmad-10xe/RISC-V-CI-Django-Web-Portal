import base64
import binascii
import gzip
import json
import re
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Artifact, Board, JenkinsJob, Status, TestCase, TestResult, TestRun


@login_required
def dashboard(request):
    boards = list(Board.objects.filter(enabled=True).prefetch_related("jobs"))
    for board in boards:
        board.latest_run = (
            TestRun.objects.filter(job__board=board)
            .select_related("job")
            .order_by("-updated_at", "-id")
            .first()
        )
        board.suite_summaries = []
        if board.latest_run:
            summaries = {
                item["test_case__category"]: item
                for item in board.latest_run.test_results.values("test_case__category").annotate(
                    executed=Count(
                        "id",
                        filter=Q(
                            hardware_status__in=[Status.PASS, Status.FAIL, Status.SKIPPED]
                        ),
                    ),
                    passed=Count("id", filter=Q(hardware_status=Status.PASS)),
                    failed=Count("id", filter=Q(hardware_status=Status.FAIL)),
                )
            }
            for category in ("Privileged", "Non-Privileged"):
                values = summaries.get(category, {})
                executed = values.get("executed", 0)
                passed = values.get("passed", 0)
                board.suite_summaries.append(
                    {
                        "name": category,
                        "executed": executed,
                        "passed": passed,
                        "failed": values.get("failed", 0),
                        "pass_percent": round(passed * 100 / executed, 1) if executed else 0,
                    }
                )
    recent_runs = TestRun.objects.select_related("job", "job__board").order_by(
        "-updated_at", "-id"
    )[:12]
    totals = TestRun.objects.aggregate(
        runs=Count("id"),
        passing=Count("id", filter=Q(status=Status.PASS)),
        failing=Count("id", filter=Q(status__in=[Status.FAIL, Status.UNSTABLE])),
        running=Count("id", filter=Q(status=Status.RUNNING)),
    )
    return render(
        request,
        "results/dashboard.html",
        {"boards": boards, "recent_runs": recent_runs, "totals": totals},
    )


@login_required
def board_detail(request, slug):
    board = get_object_or_404(Board, slug=slug)
    runs = (
        TestRun.objects.filter(job__board=board)
        .select_related("job")
        .order_by("-updated_at", "-id")
    )
    status = request.GET.get("status", "").upper()
    if status in Status.values:
        runs = runs.filter(status=status)
    return render(
        request,
        "results/board_detail.html",
        {"board": board, "runs": runs[:100], "selected_status": status},
    )


@login_required
def run_detail(request, slug, build_number):
    run = get_object_or_404(
        TestRun.objects.select_related("job", "job__board"),
        job__board__slug=slug,
        build_number=build_number,
    )
    results = run.test_results.select_related("test_case").filter(
        test_case__category="Privileged"
    )
    status = request.GET.get("status", "").upper()
    query = request.GET.get("q", "").strip()
    if status == "NOT_RUN":
        results = results.filter(hardware_status__in=[Status.SKIPPED, Status.UNKNOWN])
    elif status in Status.values:
        results = results.filter(hardware_status=status)
    if query:
        results = results.filter(test_case__name__icontains=query)
    suite_summaries = []
    for category in ("Privileged", "Non-Privileged"):
        summary = run.test_results.filter(test_case__category=category).aggregate(
            expected=Count("id"),
            completed=Count(
                "id",
                filter=Q(hardware_status__in=[Status.PASS, Status.FAIL]),
            ),
            passed=Count("id", filter=Q(hardware_status=Status.PASS)),
            failed=Count("id", filter=Q(hardware_status=Status.FAIL)),
        )
        decided = summary["passed"] + summary["failed"]
        summary.update(
            name=category,
            not_run=summary["expected"] - summary["completed"],
            pass_percent=round(summary["passed"] * 100 / decided, 1) if decided else 0,
        )
        suite_summaries.append(summary)
    return render(
        request,
        "results/run_detail.html",
        {
            "run": run,
            "results": results[:2000],
            "suite_summaries": suite_summaries,
            "selected_status": status,
            "query": query,
        },
    )


@login_required
def artifact_download(request, artifact_id):
    artifact = get_object_or_404(Artifact, id=artifact_id)
    root = settings.PORTAL_ARTIFACT_ROOT
    candidate = (root / artifact.relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Http404("Invalid artifact path") from exc
    if not candidate.is_file():
        raise Http404("Artifact is not available")
    return FileResponse(candidate.open("rb"), as_attachment=True, filename=artifact.name)


@login_required
def test_uart_download(request, result_id):
    result = get_object_or_404(TestResult.objects.select_related("test_case"), id=result_id)
    if not result.log_path or result.log_path.startswith(("http://", "https://")):
        raise Http404("UART log is not stored by the portal")
    root = settings.PORTAL_ARTIFACT_ROOT
    candidate = (root / result.log_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Http404("Invalid UART log path") from exc
    if not candidate.is_file():
        raise Http404("UART log is not available")
    return FileResponse(
        candidate.open("rb"),
        as_attachment=False,
        filename=f"{result.test_case.name}-uart.log",
        content_type="text/plain",
    )


def _safe_component(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "unnamed"


def _store_uart_log(board_slug, job_name, build_number, test_name, encoded):
    try:
        compressed = base64.b64decode(encoded, validate=True)
        content = gzip.decompress(compressed)
    except (binascii.Error, gzip.BadGzipFile, OSError, ValueError, TypeError) as exc:
        raise ValueError("invalid UART log encoding") from exc
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("UART log exceeds the 2 MiB per-test limit")
    relative = (
        "uart"
        f"/{_safe_component(board_slug)}"
        f"/{_safe_component(job_name)}"
        f"/{int(build_number)}"
        f"/{_safe_component(test_name)}.log"
    )
    destination = (settings.PORTAL_ARTIFACT_ROOT / relative).resolve()
    destination.relative_to(settings.PORTAL_ARTIFACT_ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return relative


def _authorized(request):
    configured = settings.PORTAL_INGEST_TOKEN
    supplied = request.headers.get("X-Portal-Token", "")
    return bool(configured and supplied and secrets.compare_digest(configured, supplied))


@csrf_exempt
@require_POST
def ingest_run(request):
    if not _authorized(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    try:
        payload = json.loads(request.body)
        board_data = payload["board"]
        job_data = payload["job"]
        build_number = int(payload["build_number"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JsonResponse({"error": "invalid payload"}, status=400)

    with transaction.atomic():
        board, _ = Board.objects.update_or_create(
            slug=board_data["slug"],
            defaults={
                "name": board_data.get("name", board_data["slug"]),
                "core_profile": board_data.get("core_profile", ""),
                "description": board_data.get("description", ""),
            },
        )
        job, _ = JenkinsJob.objects.update_or_create(
            name=job_data["name"],
            defaults={"board": board, "jenkins_url": job_data.get("jenkins_url", "")},
        )
        run_defaults = {
            "status": payload.get("status", Status.UNKNOWN),
            "started_at": (
                parse_datetime(payload["started_at"]) if payload.get("started_at") else None
            ),
            "finished_at": (
                parse_datetime(payload["finished_at"])
                if payload.get("finished_at")
                else None
            ),
            "expected_cases": int(payload.get("expected_cases", 0)),
            "completed_cases": int(payload.get("completed_cases", 0)),
            "passed_cases": int(payload.get("passed_cases", 0)),
            "failed_cases": int(payload.get("failed_cases", 0)),
            "skipped_cases": int(payload.get("skipped_cases", 0)),
            "git_revision": payload.get("git_revision", ""),
            "act_revision": payload.get("act_revision", ""),
            "parameters": payload.get("parameters", {}),
            "metadata": payload.get("metadata", {}),
        }
        run, created = TestRun.objects.update_or_create(
            job=job, build_number=build_number, defaults=run_defaults
        )
        for item in payload.get("results", []):
            test_case, _ = TestCase.objects.update_or_create(
                name=item["name"],
                defaults={
                    "category": item.get("category", ""),
                    "extension": item.get("extension", ""),
                },
            )
            log_path = item.get("log_path", "")
            if item.get("uart_log_gzip_b64"):
                try:
                    log_path = _store_uart_log(
                        board.slug,
                        job.name,
                        build_number,
                        item["name"],
                        item["uart_log_gzip_b64"],
                    )
                except ValueError as exc:
                    return JsonResponse({"error": str(exc)}, status=400)
            TestResult.objects.update_or_create(
                run=run,
                test_case=test_case,
                defaults={
                    "sail_status": item.get("sail_status", Status.UNKNOWN),
                    "spike_status": item.get("spike_status", Status.UNKNOWN),
                    "hardware_status": item.get("hardware_status", Status.UNKNOWN),
                    "duration_seconds": item.get("duration_seconds"),
                    "failure_reason": item.get("failure_reason", ""),
                    "log_path": log_path,
                },
            )
        for item in payload.get("artifacts", []):
            Artifact.objects.update_or_create(
                run=run,
                name=item["name"],
                defaults={
                    "relative_path": item["relative_path"],
                    "external_url": item.get("external_url", ""),
                    "kind": item.get("kind", ""),
                    "size_bytes": int(item.get("size_bytes", 0)),
                    "sha256": item.get("sha256", ""),
                },
            )
    return JsonResponse(
        {"id": run.id, "url": run.get_absolute_url(), "created": created},
        status=201 if created else 200,
    )
