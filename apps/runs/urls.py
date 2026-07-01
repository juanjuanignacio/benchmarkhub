from django.urls import path
from . import views

app_name = 'runs'

urlpatterns = [
    path('', views.RunListView.as_view(), name='list'),
    path('create/', views.RunCreateView.as_view(), name='create'),
    path('compare/', views.compare_view, name='compare'),
    path('ab-test/', views.ab_test_view, name='ab_test'),
    path('ab-results/<str:ab_test_id>/', views.ab_results_view, name='ab_results'),
    path('model-history/', views.model_history_view, name='model_history'),
    path('suite-runs/<int:pk>/', views.suite_run_detail_view, name='suite_run_detail'),
    path('scheduled/', views.scheduled_list_view, name='scheduled_list'),
    path('scheduled/create/', views.scheduled_create_view, name='scheduled_create'),
    path('scheduled/<int:pk>/delete/', views.scheduled_delete_view, name='scheduled_delete'),
    path('scheduled/<int:pk>/toggle/', views.scheduled_toggle_view, name='scheduled_toggle'),
    path('estimate-cost/', views.estimate_cost_view, name='estimate_cost'),
    path('import-csv/', views.import_csv_view, name='import_csv'),
    # Run templates
    path('templates/', views.template_list_view, name='template_list'),
    path('templates/create/', views.template_create_view, name='template_create'),
    path('templates/<int:pk>/delete/', views.template_delete_view, name='template_delete'),
    path('templates/<int:pk>/apply/', views.template_apply_api, name='template_apply'),
    # Parameter sweep & bulk run
    path('sweep/', views.parameter_sweep_view, name='parameter_sweep'),
    path('bulk/', views.bulk_run_view, name='bulk_run'),
    # Per-run actions (keep at end — <int:pk> is a catch-all)
    path('<int:pk>/', views.RunDetailView.as_view(), name='detail'),
    path('<int:pk>/results/', views.RunResultsView.as_view(), name='results'),
    path('<int:pk>/delete/', views.delete_run_view, name='delete'),
    path('<int:pk>/cancel/', views.cancel_run_view, name='cancel'),
    path('<int:pk>/status/', views.run_status_api, name='status_api'),
    path('<int:pk>/export-csv/', views.export_run_csv, name='export_csv'),
    path('<int:pk>/export-excel/', views.export_run_excel, name='export_excel'),
    path('<int:pk>/retry-failed/', views.retry_failed_view, name='retry_failed'),
]
