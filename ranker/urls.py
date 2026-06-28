from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("results/", views.results_view, name="results"),
    path("results/<int:run_id>/", views.results_view, name="results_run"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("analytics/<int:run_id>/", views.analytics_view, name="analytics_run"),
    path("api/run/", views.run_ranking, name="api_run"),
    path("api/status/<str:task_id>/", views.task_status, name="api_status"),
    path("api/stats/", views.api_stats, name="api_stats"),
    path("api/candidate/<str:candidate_id>/", views.candidate_detail_api, name="api_candidate"),
    path("download/<int:run_id>/", views.download_submission, name="download"),
]
