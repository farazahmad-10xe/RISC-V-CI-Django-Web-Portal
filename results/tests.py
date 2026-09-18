import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Artifact, Board, JenkinsJob, TestRun


class PortalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("viewer", password="safe-test-password")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    @override_settings(PORTAL_INGEST_TOKEN="test-token")
    def test_ingest_creates_run_and_results(self):
        payload = {
            "board": {"slug": "vf2", "name": "VisionFive 2", "core_profile": "U74"},
            "job": {"name": "vf2-privileged-weekly"},
            "build_number": 3,
            "status": "RUNNING",
            "expected_cases": 485,
            "completed_cases": 6,
            "results": [
                {
                    "name": "ExceptionsM-01",
                    "category": "Privileged",
                    "hardware_status": "PASS",
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
        self.assertEqual(TestRun.objects.get().test_results.count(), 1)

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
