#!/usr/bin/env python3
"""Merge ACT Jenkins outputs and publish one build to the results portal."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STATUS_MAP = {
    "SUCCESS": "PASS",
    "PASSED": "PASS",
    "PASS": "PASS",
    "FAILURE": "FAIL",
    "FAILED": "FAIL",
    "FAIL": "FAIL",
    "UNSTABLE": "UNSTABLE",
    "ABORTED": "ABORTED",
    "RUNNING": "RUNNING",
    "QUEUED": "QUEUED",
    "SKIP": "SKIPPED",
    "SKIPPED": "SKIPPED",
    "NOT RUN": "SKIPPED",
    "NOT_RUN": "SKIPPED",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--board-slug", required=True)
    parser.add_argument("--board-name", required=True)
    parser.add_argument("--core-profile", default="")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--build-number", type=int, required=True)
    parser.add_argument("--build-url", default="")
    parser.add_argument("--status", default="AUTO")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--finished-at", default="")
    parser.add_argument("--portal-url", default="https://192.168.100.150/portal/")
    parser.add_argument("--token", default=os.getenv("PORTAL_INGEST_TOKEN", ""))
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-post", action="store_true")
    return parser.parse_args()


def normalize_status(value: object, default: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    return STATUS_MAP.get(text, text if text in set(STATUS_MAP.values()) else default)


def read_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("'\"")
    return values


def read_status_tsv(path: Path) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not path.is_file():
        return statuses
    with path.open(newline="", encoding="utf-8", errors="replace") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            if len(row) < 2 or not row[0] or row[0] == "test_name":
                continue
            statuses[row[0]] = normalize_status(row[1])
    return statuses


def read_cases(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError(f"{path} must contain a JSON list")
    return {
        str(item["test_name"]): item
        for item in loaded
        if isinstance(item, dict) and item.get("test_name")
    }


def extension_for(name: str) -> str:
    return re.sub(r"-\d+$", "", name)


def build_payload(args: argparse.Namespace) -> dict:
    state_root = args.state_root.resolve()
    run_root = args.run_root.resolve()
    state = read_state(state_root / "state.env")
    sail = read_status_tsv(state_root / "sail_reference_status.tsv")
    spike = read_status_tsv(state_root / "spike_status.tsv")
    cases = read_cases(run_root / "cases.json")
    names = sorted(set(sail) | set(spike) | set(cases), key=str.casefold)

    results = []
    hardware_counts: Counter[str] = Counter()
    for name in names:
        case = cases.get(name, {})
        hardware_status = normalize_status(case.get("status"))
        if name in cases:
            hardware_counts[hardware_status] += 1
        results.append(
            {
                "name": name,
                "extension": extension_for(name),
                "sail_status": sail.get(name, normalize_status(case.get("sail_status"))),
                "spike_status": spike.get(name, "UNKNOWN"),
                "hardware_status": hardware_status,
                "failure_reason": (
                    str(case.get("root_cause", "")) if hardware_status == "FAIL" else ""
                ),
                "log_path": str(case.get("report", "")),
            }
        )

    expected = int(state.get("EXPECTED_CASES", "0") or 0)
    completed = len(cases)
    requested_status = args.status.strip().upper()
    if requested_status == "AUTO":
        if not cases or (expected and completed < expected):
            run_status = "RUNNING"
        elif hardware_counts["FAIL"]:
            run_status = "UNSTABLE"
        else:
            run_status = "PASS"
    else:
        run_status = normalize_status(requested_status)

    payload = {
        "board": {
            "slug": args.board_slug,
            "name": args.board_name,
            "core_profile": args.core_profile,
        },
        "job": {
            "name": args.job_name,
            "jenkins_url": args.build_url.rsplit("/", 2)[0] + "/" if args.build_url else "",
        },
        "build_number": args.build_number,
        "status": run_status,
        "expected_cases": expected or len(names),
        "completed_cases": completed,
        "passed_cases": hardware_counts["PASS"],
        "failed_cases": hardware_counts["FAIL"],
        "skipped_cases": hardware_counts["SKIPPED"],
        "act_revision": state.get("ACT_REVISION", ""),
        "parameters": {"test_scope": state.get("TEST_SCOPE", "")},
        "metadata": {
            "run_id": state.get("RUN_ID", run_root.name),
            "run_kind": state.get("RUN_KIND", ""),
            "build_url": args.build_url,
        },
        "results": results,
    }
    if args.started_at:
        payload["started_at"] = args.started_at
    if args.finished_at:
        payload["finished_at"] = args.finished_at
    return payload


def publish(payload: dict, args: argparse.Namespace) -> dict:
    if not args.token:
        raise ValueError("No token supplied; use --token or PORTAL_INGEST_TOKEN")
    endpoint = args.portal_url.rstrip("/") + "/api/v1/runs/"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Portal-Token": args.token},
        method="POST",
    )
    context = ssl.create_default_context(cafile=str(args.ca_file) if args.ca_file else None)
    try:
        with urlopen(request, context=context, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Portal returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach portal: {exc.reason}") from exc


def main() -> int:
    args = parse_args()
    try:
        payload = build_payload(args)
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        if args.no_post:
            print(rendered)
        else:
            response = publish(payload, args)
            print(json.dumps(response, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
