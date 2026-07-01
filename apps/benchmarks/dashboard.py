import logging
from datetime import timedelta

from django.db.models import Avg, Count, Max, Q
from django.shortcuts import render
from django.utils import timezone

from apps.benchmarks.models import Benchmark
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun, RunResult

logger = logging.getLogger(__name__)


def dashboard_view(request):
    # Core stats
    total_benchmarks = Benchmark.objects.count()
    loaded_benchmarks = Benchmark.objects.filter(loaded_at__isnull=False).count()
    total_providers = Provider.objects.filter(is_active=True).count()
    total_runs = BenchmarkRun.objects.count()
    completed_runs = BenchmarkRun.objects.filter(status='completed').count()
    total_questions_answered = RunResult.objects.count()

    # Average score across completed runs
    avg_score_result = BenchmarkRun.objects.filter(status='completed').aggregate(avg=Avg('score'))
    avg_score = avg_score_result['avg'] or 0.0

    # Recent 10 completed runs
    recent_runs = (
        BenchmarkRun.objects.filter(status='completed')
        .select_related('benchmark', 'provider')
        .order_by('-completed_at')[:10]
    )

    # Best scores per benchmark
    best_scores = []
    benchmarks_with_runs = (
        Benchmark.objects.filter(runs__status='completed')
        .distinct()
        .order_by('name')
    )
    for bench in benchmarks_with_runs:
        best_run = (
            BenchmarkRun.objects.filter(benchmark=bench, status='completed')
            .select_related('provider')
            .order_by('-score')
            .first()
        )
        if best_run:
            best_scores.append({
                'benchmark': bench,
                'score': best_run.score,
                'model_name': best_run.model_name,
                'provider': best_run.provider,
                'date': best_run.completed_at,
                'run': best_run,
            })

    # Runs per day for last 14 days
    today = timezone.now().date()
    runs_by_day = []
    runs_by_day_labels = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        count = BenchmarkRun.objects.filter(
            created_at__date=day
        ).count()
        runs_by_day.append(count)
        runs_by_day_labels.append(day.strftime('%b %d'))

    # Top 10 models by average score
    top_models = (
        BenchmarkRun.objects.filter(status='completed')
        .values('model_name')
        .annotate(
            avg_score=Avg('score'),
            run_count=Count('id'),
        )
        .order_by('-avg_score')[:10]
    )

    # Benchmark coverage: which benchmarks (from registry) have runs
    from apps.benchmarks.registry import BENCHMARK_REGISTRY
    benchmark_coverage = []
    for slug, loader_cls in BENCHMARK_REGISTRY.items():
        loader = loader_cls()
        try:
            bench = Benchmark.objects.get(slug=slug)
            has_runs = bench.runs.filter(status='completed').exists()
            run_count = bench.runs.filter(status='completed').count()
            best_run = bench.runs.filter(status='completed').order_by('-score').first()
        except Benchmark.DoesNotExist:
            bench = None
            has_runs = False
            run_count = 0
            best_run = None
        benchmark_coverage.append({
            'slug': slug,
            'name': loader.name,
            'category': loader.category,
            'benchmark': bench,
            'has_runs': has_runs,
            'run_count': run_count,
            'best_score': best_run.score if best_run else None,
            'is_loaded': bench is not None and bench.is_loaded,
        })

    context = {
        'total_benchmarks': total_benchmarks,
        'loaded_benchmarks': loaded_benchmarks,
        'total_providers': total_providers,
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'total_questions_answered': total_questions_answered,
        'avg_score': avg_score,
        'recent_runs': recent_runs,
        'best_scores': best_scores,
        'runs_by_day': runs_by_day,
        'runs_by_day_labels': runs_by_day_labels,
        'top_models': list(top_models),
        'benchmark_coverage': benchmark_coverage,
    }
    return render(request, 'dashboard.html', context)
