from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("boards/<slug:slug>/", views.board_detail, name="board-detail"),
    path("boards/<slug:slug>/runs/<int:build_number>/", views.run_detail, name="run-detail"),
    path(
        "boards/<slug:slug>/runs/<int:build_number>/delete/",
        views.delete_run,
        name="run-delete",
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
