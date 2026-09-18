from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from results.models import Board, JenkinsJob, Status, TestCase, TestResult, TestRun


class Command(BaseCommand):
    help = "Create representative VF2 and BPI-F3 dashboard data"

    def handle(self, *args, **options):
        now = timezone.now()
        fixtures = [
            (
                "vf2",
                "VisionFive 2",
                "SiFive U74",
                "vf2-privileged-weekly",
                3,
                Status.RUNNING,
                485,
                6,
            ),
            (
                "bpif3",
                "Banana Pi F3",
                "SpacemiT X60",
                "bpif3-privileged-weekly",
                2,
                Status.PASS,
                485,
                485,
            ),
        ]
        for slug, name, core, job_name, build, status, expected, completed in fixtures:
            board, _ = Board.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "core_profile": core,
                    "description": "ACT hardware validation board",
                },
            )
            job, _ = JenkinsJob.objects.update_or_create(
                name=job_name,
                defaults={
                    "board": board,
                    "jenkins_url": f"https://192.168.100.150/job/{job_name}/",
                },
            )
            run, _ = TestRun.objects.update_or_create(
                job=job,
                build_number=build,
                defaults={
                    "status": status,
                    "started_at": now - timedelta(hours=3),
                    "finished_at": None if status == Status.RUNNING else now - timedelta(hours=1),
                    "expected_cases": expected,
                    "completed_cases": completed,
                    "passed_cases": completed - 1 if completed else 0,
                    "failed_cases": 1 if completed else 0,
                    "git_revision": "d34db33f" * 5,
                    "act_revision": "a17c0de" * 5,
                },
            )
            for index in range(1, min(completed, 12) + 1):
                case, _ = TestCase.objects.update_or_create(
                    name=f"ExceptionsM-{index:02d}",
                    defaults={"category": "Privileged", "extension": "ExceptionsM"},
                )
                TestResult.objects.update_or_create(
                    run=run,
                    test_case=case,
                    defaults={
                        "sail_status": Status.PASS,
                        "spike_status": Status.PASS,
                        "hardware_status": Status.FAIL if index == 4 else Status.PASS,
                        "duration_seconds": 2.1 + index / 10,
                        "failure_reason": "Signature mismatch" if index == 4 else "",
                    },
                )
        self.stdout.write(self.style.SUCCESS("Demo VF2 and BPI-F3 data created."))
