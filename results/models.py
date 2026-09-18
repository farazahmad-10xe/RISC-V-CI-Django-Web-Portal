from django.db import models
from django.urls import reverse


class Status(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    UNSTABLE = "UNSTABLE", "Unstable"
    SKIPPED = "SKIPPED", "Skipped"
    ABORTED = "ABORTED", "Aborted"
    UNKNOWN = "UNKNOWN", "Unknown"


class Board(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    core_profile = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("board-detail", kwargs={"slug": self.slug})


class JenkinsJob(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="jobs")
    name = models.CharField(max_length=160, unique=True)
    jenkins_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TestRun(models.Model):
    job = models.ForeignKey(JenkinsJob, on_delete=models.CASCADE, related_name="runs")
    build_number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expected_cases = models.PositiveIntegerField(default=0)
    completed_cases = models.PositiveIntegerField(default=0)
    passed_cases = models.PositiveIntegerField(default=0)
    failed_cases = models.PositiveIntegerField(default=0)
    skipped_cases = models.PositiveIntegerField(default=0)
    git_revision = models.CharField(max_length=64, blank=True)
    act_revision = models.CharField(max_length=64, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-build_number"]
        constraints = [
            models.UniqueConstraint(fields=["job", "build_number"], name="unique_job_build")
        ]

    def __str__(self):
        return f"{self.job.name} #{self.build_number}"

    def get_absolute_url(self):
        return reverse(
            "run-detail",
            kwargs={"slug": self.job.board.slug, "build_number": self.build_number},
        )

    @property
    def progress_percent(self):
        if not self.expected_cases:
            return 0
        return min(100, round(self.completed_cases * 100 / self.expected_cases))

    @property
    def pass_percent(self):
        decided = self.passed_cases + self.failed_cases
        return round(self.passed_cases * 100 / decided, 1) if decided else 0


class TestCase(models.Model):
    name = models.CharField(max_length=300, unique=True)
    category = models.CharField(max_length=80, blank=True, db_index=True)
    extension = models.CharField(max_length=80, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TestResult(models.Model):
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name="test_results")
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name="results")
    sail_status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    spike_status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    hardware_status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.UNKNOWN,
    )
    duration_seconds = models.FloatField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    log_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["test_case__name"]
        constraints = [
            models.UniqueConstraint(fields=["run", "test_case"], name="unique_result_per_run")
        ]

    def __str__(self):
        return f"{self.run}: {self.test_case.name}"


class Artifact(models.Model):
    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name="artifacts")
    name = models.CharField(max_length=200)
    relative_path = models.CharField(max_length=500)
    kind = models.CharField(max_length=40, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["run", "name"], name="unique_artifact_name_per_run")
        ]

    def __str__(self):
        return self.name
