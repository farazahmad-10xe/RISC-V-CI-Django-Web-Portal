from django.contrib import admin

from .models import Artifact, Board, JenkinsJob, TestCase, TestResult, TestRun


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "core_profile", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "slug", "core_profile")


@admin.register(JenkinsJob)
class JenkinsJobAdmin(admin.ModelAdmin):
    list_display = ("name", "board", "enabled")
    list_filter = ("board", "enabled")
    search_fields = ("name",)


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = (
        "job",
        "build_number",
        "status",
        "completed_cases",
        "expected_cases",
        "updated_at",
    )
    list_filter = ("status", "job__board")
    search_fields = ("job__name", "git_revision", "act_revision")


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "extension")
    list_filter = ("category", "extension")
    search_fields = ("name",)


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ("test_case", "run", "sail_status", "spike_status", "hardware_status")
    list_filter = ("hardware_status", "sail_status", "spike_status", "run__job__board")
    search_fields = ("test_case__name", "failure_reason")


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ("name", "run", "kind", "size_bytes")
    search_fields = ("name", "relative_path", "external_url")
