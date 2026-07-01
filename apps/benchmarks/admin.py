from django.contrib import admin
from .models import Benchmark, BenchmarkQuestion


@admin.register(Benchmark)
class BenchmarkAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'category', 'num_questions', 'loaded_at', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['loaded_at', 'num_questions']


@admin.register(BenchmarkQuestion)
class BenchmarkQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_id', 'benchmark', 'subject', 'difficulty', 'correct_answer']
    list_filter = ['benchmark', 'subject', 'difficulty']
    search_fields = ['question', 'question_id']
    raw_id_fields = ['benchmark']
