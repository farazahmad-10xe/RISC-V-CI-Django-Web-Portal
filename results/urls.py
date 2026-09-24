from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("boards/<slug:slug>/", views.board_detail, name="board-detail"),
    path(
        "boards/<slug:slug>/jobs/<str:job_name>/runs/<int:build_number>/",
        views.run_detail,
        name="run-detail",
    ),
    path(
        "boards/<slug:slug>/jobs/<str:job_name>/runs/<int:build_number>/workbook/",
        views.run_workbook,
        name="run-workbook",
    ),
    path(
        "boards/<slug:slug>/jobs/<str:job_name>/runs/<int:build_number>/workbook/columns/add/",
        views.add_analysis_column,
        name="analysis-column-add",
    ),
    path(
        "boards/<slug:slug>/jobs/<str:job_name>/runs/<int:build_number>/workbook/columns/<int:column_id>/save/",
        views.save_analysis_column,
        name="analysis-column-save",
    ),
    path(
        "boards/<slug:slug>/jobs/<str:job_name>/runs/<int:build_number>/delete/",
        views.delete_run,
        name="run-delete",
    ),
    path(
        "boards/<slug:slug>/runs/<int:build_number>/",
        views.legacy_run_detail,
        name="legacy-run-detail",
    ),
    path(
        "artifacts/<int:artifact_id>/download/",
        views.artifact_download,
        name="artifact-download",
    ),
    path(
        "results/<int:result_id>/uart/",
        views.test_uart_download,
        name="test-uart-download",
    ),
    path("api/v1/runs/", views.ingest_run, name="api-ingest-run"),
]
