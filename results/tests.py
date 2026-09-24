import base64
import gzip
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    AnalysisColumn,
    AnalysisValue,
    Artifact,
    Board,
    JenkinsJob,
    Status,
    TestResult,
    TestRun,
)
from .models import TestCase as ACTTestCase


class PortalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("viewer", password="safe-test-password")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_dashboard_shows_suite_results_for_each_board(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=1)
        passing = ACTTestCase.objects.create(name="ExceptionsM-01", category="Privileged")
        failing = ACTTestCase.objects.create(name="I-add-01", category="Non-Privileged")
        TestResult.objects.create(
            run=run,
            test_case=passing,
            hardware_status=Status.PASS,
        )
        TestResult.objects.create(
            run=run,
            test_case=failing,
            hardware_status=Status.FAIL,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Privileged")
        self.assertContains(response, "Non-Privileged")
        self.assertContains(response, "1 passed · 0 failed · 1 executed")
        self.assertContains(response, "0 passed · 1 failed · 1 executed")

    def test_run_detail_not_run_filter_includes_skipped_and_unknown(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=3)
        for name, status in (
            ("PassedM-01", Status.PASS),
            ("SkippedM-01", Status.SKIPPED),
            ("MissingM-01", Status.UNKNOWN),
        ):
            test_case = ACTTestCase.objects.create(name=name, category="Privileged")
            TestResult.objects.create(
                run=run,
                test_case=test_case,
                hardware_status=status,
            )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("run-detail", args=["vf2", "vf2-job", 3]),
            {"status": "NOT_RUN"},
        )
        self.assertContains(response, "SkippedM-01")
        self.assertContains(response, "MissingM-01")
        self.assertNotContains(response, "PassedM-01")
        self.assertContains(response, "Not Run (Skipped + Unknown)")

    def test_same_build_number_from_two_jobs_has_distinct_run_urls(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        sanity = JenkinsJob.objects.create(board=board, name="vf2-uart-sanity")
        weekly = JenkinsJob.objects.create(board=board, name="vf2-uart-weekly")
        sanity_run = TestRun.objects.create(job=sanity, build_number=1)
        weekly_run = TestRun.objects.create(job=weekly, build_number=1)

        self.assertNotEqual(sanity_run.get_absolute_url(), weekly_run.get_absolute_url())
        self.client.force_login(self.user)
        sanity_response = self.client.get(sanity_run.get_absolute_url())
        weekly_response = self.client.get(weekly_run.get_absolute_url())
        self.assertContains(sanity_response, "vf2-uart-sanity")
        self.assertContains(weekly_response, "vf2-uart-weekly")

        legacy = self.client.get(reverse("legacy-run-detail", args=["vf2", 1]))
        self.assertRedirects(legacy, weekly_run.get_absolute_url())

    def test_non_staff_user_cannot_delete_run(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=4)

        self.client.force_login(self.user)
        detail = self.client.get(reverse("run-detail", args=["vf2", "vf2-job", 4]))
        self.assertNotContains(detail, "Delete from portal")
        response = self.client.post(reverse("run-delete", args=["vf2", "vf2-job", 4]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(TestRun.objects.filter(id=run.id).exists())

    def test_staff_user_can_delete_run_and_portal_uart_files(self):
        staff = get_user_model().objects.create_user(
            "operator", password="safe-test-password", is_staff=True
        )
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=4)
        test_case = ACTTestCase.objects.create(name="ExceptionsM-01")
        result = TestResult.objects.create(run=run, test_case=test_case)
        Artifact.objects.create(run=run, name="summary", relative_path="summary.md")

        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary).resolve()
            uart_directory = artifact_root / "uart" / "vf2" / "vf2-job" / "4"
            uart_directory.mkdir(parents=True)
            (uart_directory / "ExceptionsM-01.log").write_text("no test run")

            self.client.force_login(staff)
            detail = self.client.get(reverse("run-detail", args=["vf2", "vf2-job", 4]))
            self.assertContains(detail, "Delete from portal")
            self.assertContains(detail, "Cancel")
            self.assertContains(detail, "OK, delete")
            with override_settings(PORTAL_ARTIFACT_ROOT=artifact_root):
                response = self.client.post(
                    reverse("run-delete", args=["vf2", "vf2-job", 4])
                )

            self.assertRedirects(response, reverse("board-detail", args=["vf2"]))
            self.assertFalse(uart_directory.exists())

        self.assertFalse(TestRun.objects.filter(id=run.id).exists())
        self.assertFalse(TestResult.objects.filter(id=result.id).exists())
        self.assertFalse(Artifact.objects.filter(run_id=run.id).exists())

    def test_workbook_execution_results_are_read_only_for_viewer(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=8)
        test_case = ACTTestCase.objects.create(
            name="ExceptionsM-01", category="Privileged", extension="ExceptionsM"
        )
        TestResult.objects.create(
            run=run,
            test_case=test_case,
            sail_status=Status.PASS,
            spike_status=Status.PASS,
            hardware_status=Status.FAIL,
            failure_reason="hardware mismatch",
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("run-workbook", args=["vf2", "vf2-job", 8])
        )

        self.assertContains(response, "ExceptionsM-01")
        self.assertContains(response, "hardware mismatch")
        self.assertNotContains(response, "Add an analysis column")
        denied = self.client.post(
            reverse("analysis-column-add", args=["vf2", "vf2-job", 8]),
            {"name": "Owner"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_authorized_user_can_add_and_save_analysis_column(self):
        editor = get_user_model().objects.create_user(
            "report-editor", password="safe-test-password"
        )
        editor.user_permissions.add(
            Permission.objects.get(codename="manage_failure_analysis")
        )
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=9)
        test_case = ACTTestCase.objects.create(
            name="ExceptionsS-00", category="Privileged", extension="ExceptionsS"
        )
        result = TestResult.objects.create(
            run=run,
            test_case=test_case,
            hardware_status=Status.FAIL,
        )

        self.client.force_login(editor)
        created = self.client.post(
            reverse("analysis-column-add", args=["vf2", "vf2-job", 9]),
            {"name": "Investigation notes"},
        )
        column = AnalysisColumn.objects.get(run=run)
        self.assertRedirects(
            created,
            f'{reverse("run-workbook", args=["vf2", "vf2-job", 9])}?edit={column.id}',
        )

        saved = self.client.post(
            reverse("analysis-column-save", args=["vf2", "vf2-job", 9, column.id]),
            {f"analysis_{result.id}": "Needs trap-log review", "suite": "Privileged"},
        )
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(
            AnalysisValue.objects.get(column=column, test_result=result).value,
            "Needs trap-log review",
        )
        result.refresh_from_db()
        self.assertEqual(result.hardware_status, Status.FAIL)

    @override_settings(PORTAL_INGEST_TOKEN="test-token")
    def test_ingest_creates_run_and_results(self):
        payload = {
            "board": {"slug": "vf2", "name": "VisionFive 2", "core_profile": "U74"},
            "job": {"name": "vf2-privileged-weekly"},
            "build_number": 3,
            "status": "RUNNING",
            "expected_cases": 485,
            "completed_cases": 6,
            "git_revision": "runner123",
            "act_revision": "act456",
            "metadata": {"sail_version": "0.14"},
            "results": [
                {
                    "name": "ExceptionsM-01",
                    "category": "Privileged",
                    "hardware_status": "PASS",
                    "log_path": "https://jenkins/artifact/uart.log",
                },
                {
                    "name": "I-add-01",
                    "category": "Non-Privileged",
                    "hardware_status": "PASS",
                }
            ],
            "artifacts": [
                {
                    "name": "summary.md",
                    "relative_path": "/agent/results/summary.md",
                    "external_url": "https://jenkins/artifact/summary.md",
                }
            ],
        }
        response = self.client.post(
            reverse("api-ingest-run"),
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Portal-Token": "test-token"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TestRun.objects.get().expected_cases, 485)
        self.assertEqual(TestRun.objects.get().test_results.count(), 2)

        self.client.force_login(self.user)
        detail = self.client.get(
            reverse("run-detail", args=["vf2", "vf2-privileged-weekly", 3])
        )
        self.assertContains(detail, "Sail version")
        self.assertContains(detail, "0.14")
        self.assertContains(detail, "runner123")
        self.assertContains(detail, "ExceptionsM-01")
        self.assertNotContains(detail, "I-add-01")
        self.assertContains(detail, "https://jenkins/artifact/uart.log")
        self.assertContains(detail, "https://jenkins/artifact/summary.md")

        payload["completed_cases"] = 7
        response = self.client.post(
            reverse("api-ingest-run"),
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Portal-Token": "test-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["created"])
        self.assertEqual(TestRun.objects.get().completed_cases, 7)

    def test_artifact_cannot_escape_root(self):
        board = Board.objects.create(slug="vf2", name="VisionFive 2")
        job = JenkinsJob.objects.create(board=board, name="vf2-job")
        run = TestRun.objects.create(job=job, build_number=1)
        artifact = Artifact.objects.create(run=run, name="secret", relative_path="../secret")
        self.client.force_login(self.user)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary, "artifacts")
            root.mkdir()
            Path(temporary, "secret").write_text("no")
            with override_settings(PORTAL_ARTIFACT_ROOT=root.resolve()):
                response = self.client.get(reverse("artifact-download", args=[artifact.id]))
        self.assertEqual(response.status_code, 404)

    @override_settings(PORTAL_INGEST_TOKEN="test-token")
    def test_ingested_uart_log_is_served_by_authenticated_portal(self):
        uart_content = b"Booting VF2\nPASS ExceptionsM-01\n"
        payload = {
            "board": {"slug": "vf2", "name": "VisionFive 2"},
            "job": {"name": "vf2-privileged-weekly"},
            "build_number": 3,
            "results": [
                {
                    "name": "ExceptionsM-01",
                    "category": "Privileged",
                    "hardware_status": "PASS",
                    "uart_log_gzip_b64": base64.b64encode(
                        gzip.compress(uart_content)
                    ).decode("ascii"),
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary).resolve()
            with override_settings(PORTAL_ARTIFACT_ROOT=artifact_root):
                response = self.client.post(
                    reverse("api-ingest-run"),
                    data=json.dumps(payload),
                    content_type="application/json",
                    headers={"X-Portal-Token": "test-token"},
                )
                self.assertEqual(response.status_code, 201)
                result = TestResult.objects.get()
                self.assertTrue(result.log_path.startswith("uart/vf2/"))

                anonymous = self.client.get(reverse("test-uart-download", args=[result.id]))
                self.assertEqual(anonymous.status_code, 302)
                self.client.force_login(self.user)
                downloaded = self.client.get(
                    reverse("test-uart-download", args=[result.id])
                )
                self.assertEqual(downloaded.status_code, 200)
                self.assertEqual(b"".join(downloaded.streaming_content), uart_content)
