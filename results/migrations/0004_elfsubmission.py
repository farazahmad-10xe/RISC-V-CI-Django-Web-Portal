import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import results.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("results", "0003_analysiscolumn_analysisvalue_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ElfSubmission",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("elf", models.FileField(upload_to=results.models.elf_upload_path)),
                ("original_name", models.CharField(max_length=255)),
                ("sha256", models.CharField(max_length=64)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("download_token_hash", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Running"),
                            ("PASS", "Pass"),
                            ("FAIL", "Fail"),
                            ("UNSTABLE", "Unstable"),
                            ("SKIPPED", "Skipped"),
                            ("ABORTED", "Aborted"),
                            ("UNKNOWN", "Unknown"),
                        ],
                        default="QUEUED",
                        max_length=16,
                    ),
                ),
                ("jenkins_queue_url", models.URLField(blank=True, max_length=1000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "board",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="elf_submissions",
                        to="results.board",
                    ),
                ),
                (
                    "run",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="elf_submission",
                        to="results.testrun",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="elf_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
