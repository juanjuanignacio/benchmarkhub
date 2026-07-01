from django.urls import path
from . import api_views

urlpatterns = [
    # Benchmarks
    path('benchmarks/', api_views.api_benchmark_list),
    path('benchmarks/<slug:slug>/', api_views.api_benchmark_detail),
    path('benchmarks/<slug:slug>/questions/', api_views.api_benchmark_questions),

    # Runs
    path('runs/', api_views.api_run_list_create),
    path('runs/<int:pk>/', api_views.api_run_detail),
    path('runs/<int:pk>/status/', api_views.api_run_status),
    path('runs/<int:pk>/cancel/', api_views.api_run_cancel),
    path('runs/<int:pk>/delete/', api_views.api_run_delete),
    path('runs/<int:pk>/results/', api_views.api_run_results),

    # Providers
    path('providers/', api_views.api_provider_list),

    # Leaderboard
    path('leaderboard/', api_views.api_leaderboard),
]
