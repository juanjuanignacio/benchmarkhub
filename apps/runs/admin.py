from django.contrib import admin
from .models import BenchmarkRun, RunResult


@admin.register(BenchmarkRun)
class BenchmarkRunAdmin(admin.ModelAdmin):
    list_display = ['benchmark', 'provider', 'model_name', 'status', 'score', 'total_questions', 'created_at']
    list_filter = ['status', 'benchmark', 'provider']
    search_fields = ['model_name', 'benchmark__name']
    readonly_fields = ['created_at', 'started_at', 'completed_at', 'score', 'total_questions', 'correct_answers']


@admin.register(RunResult)
class RunResultAdmin(admin.ModelAdmin):
    list_display = ['run', 'question', 'parsed_answer', 'is_correct', 'response_time', 'created_at']
    list_filter = ['is_correct', 'run__benchmark']
    search_fields = ['model_response', 'parsed_answer']
    raw_id_fields = ['run', 'question']
    readonly_fields = ['created_at']
