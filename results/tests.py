import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Artifact, Board, JenkinsJob, Status, TestResult, TestRun
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
        detail = self.client.get(reverse("run-detail", args=["vf2", 3]))
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
