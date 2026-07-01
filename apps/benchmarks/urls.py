from django.urls import path
from . import views
from . import suite_views

app_name = 'benchmarks'

urlpatterns = [
    path('', views.BenchmarkListView.as_view(), name='list'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('custom/', views.create_custom_benchmark, name='custom'),
    path('custom/example-csv/', views.download_example_csv, name='example_csv'),
    path('rag/', views.create_rag_benchmark, name='rag'),
    path('rag/example-csv/', views.download_rag_example_csv, name='rag_example_csv'),
    path('hf-import/', views.hf_import_view, name='hf_import'),
    path('hardness/', views.hardness_tracker_view, name='hardness'),

    # Benchmark Suites
    path('suites/', suite_views.suite_list_view, name='suite_list'),
    path('suites/create/', suite_views.suite_create_view, name='suite_create'),
    path('suites/<int:pk>/', suite_views.suite_detail_view, name='suite_detail'),
    path('suites/<int:pk>/delete/', suite_views.suite_delete_view, name='suite_delete'),
    path('suites/<int:pk>/run/', suite_views.run_suite_view, name='run_suite'),

    # Prompt Library
    path('prompts/', views.prompt_list_view, name='prompt_list'),
    path('prompts/create/', views.prompt_create_view, name='prompt_create'),
    path('prompts/api/', views.prompt_api_view, name='prompt_api'),
    path('prompts/<int:pk>/edit/', views.prompt_edit_view, name='prompt_edit'),
    path('prompts/<int:pk>/delete/', views.prompt_delete_view, name='prompt_delete'),

    # Benchmark detail/actions (keep at end to avoid conflicts)
    path('<slug:slug>/', views.BenchmarkDetailView.as_view(), name='detail'),
    path('<slug:slug>/questions/', views.BenchmarkQuestionsView.as_view(), name='questions'),
    path('<slug:slug>/load/', views.load_benchmark_view, name='load'),
    path('<slug:slug>/delete/', views.delete_benchmark_view, name='delete'),
    path('<slug:slug>/export-csv/', views.export_questions_csv, name='export_csv'),
    path('<slug:slug>/export-excel/', views.export_questions_excel, name='export_excel'),
    path('<slug:slug>/import-answers/', views.import_answers_csv, name='import_answers'),
    path('<slug:slug>/set-prompt/', views.set_prompt_template_view, name='set_prompt'),
]
