import argparse
import json
import tempfile
import unittest
from pathlib import Path

from tools.publish_jenkins_results import build_payload, normalize_status


class PublisherTests(unittest.TestCase):
    def test_status_aliases(self):
        self.assertEqual(normalize_status("SUCCESS"), "PASS")
        self.assertEqual(normalize_status("not run"), "SKIPPED")
        self.assertEqual(normalize_status("unexpected"), "UNKNOWN")

    def test_merges_reference_and_hardware_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root = root / "state"
            run_root = root / "run"
            state_root.mkdir()
            run_root.mkdir()
            (state_root / "state.env").write_text(
                "RUN_ID=jenkins_weekly_7\nEXPECTED_CASES=2\nACT_REVISION=abc123\n"
            )
            (state_root / "sail_reference_status.tsv").write_text(
                "test_name\tsail_status\thardware_elf\nExceptionsM-01\tPASS\tyes\n"
            )
            (state_root / "spike_status.tsv").write_text("ExceptionsM-01\tPASS\n")
            (run_root / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "test_name": "ExceptionsM-01",
                            "status": "FAIL",
                            "root_cause": "Signature mismatch",
                            "report": "per_case/ExceptionsM-01/report.md",
                        }
                    ]
                )
            )
            args = argparse.Namespace(
                state_root=state_root,
                run_root=run_root,
                board_slug="vf2",
                board_name="VisionFive 2",
                core_profile="SiFive U74",
                job_name="vf2-privileged-weekly",
                build_number=7,
                build_url="https://jenkins/job/vf2-privileged-weekly/7/",
                status="AUTO",
                started_at="",
                finished_at="",
            )
            payload = build_payload(args)
        self.assertEqual(payload["status"], "RUNNING")
        self.assertEqual(payload["failed_cases"], 1)
        self.assertEqual(payload["results"][0]["sail_status"], "PASS")
        self.assertEqual(payload["results"][0]["spike_status"], "PASS")
        self.assertEqual(payload["results"][0]["hardware_status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
