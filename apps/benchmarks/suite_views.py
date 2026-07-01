import logging
import threading

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .models import Benchmark, BenchmarkSuite, BenchmarkSuiteItem

logger = logging.getLogger(__name__)


def suite_list_view(request):
    suites = BenchmarkSuite.objects.prefetch_related('items__benchmark').all()
    return render(request, 'benchmarks/suites/list.html', {'suites': suites})


def suite_create_view(request):
    benchmarks = Benchmark.objects.filter(is_active=True)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        benchmark_ids = request.POST.getlist('benchmarks')

        if not name:
            messages.error(request, 'Suite name is required.')
            return render(request, 'benchmarks/suites/create.html', {
                'benchmarks': benchmarks,
            })

        slug = slugify(name)
        base_slug = slug
        counter = 1
        while BenchmarkSuite.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        suite = BenchmarkSuite.objects.create(
            name=name,
            slug=slug,
            description=description,
        )

        for order, bid in enumerate(benchmark_ids):
            try:
                b = Benchmark.objects.get(id=bid)
                BenchmarkSuiteItem.objects.create(suite=suite, benchmark=b, order=order)
            except Benchmark.DoesNotExist:
                pass

        messages.success(request, f'Suite "{name}" created with {len(benchmark_ids)} benchmarks.')
        return redirect('benchmarks:suite_detail', pk=suite.pk)

    return render(request, 'benchmarks/suites/create.html', {'benchmarks': benchmarks})


def suite_detail_view(request, pk):
    suite = get_object_or_404(BenchmarkSuite, pk=pk)
    items = suite.items.select_related('benchmark').all()
    from apps.runs.models import BenchmarkSuiteRun
    suite_runs = BenchmarkSuiteRun.objects.filter(suite=suite).select_related('provider').order_by('-created_at')[:10]
    providers = __import__('apps.providers.models', fromlist=['Provider']).Provider.objects.filter(is_active=True)
    return render(request, 'benchmarks/suites/detail.html', {
        'suite': suite,
        'items': items,
        'suite_runs': suite_runs,
        'providers': providers,
    })


def suite_delete_view(request, pk):
    suite = get_object_or_404(BenchmarkSuite, pk=pk)
    if request.method == 'POST':
        name = suite.name
        suite.delete()
        messages.success(request, f'Suite "{name}" deleted.')
        return redirect('benchmarks:suite_list')
    return render(request, 'benchmarks/suites/delete_confirm.html', {'suite': suite})


def run_suite_view(request, pk):
    if request.method != 'POST':
        return redirect('benchmarks:suite_detail', pk=pk)

    suite = get_object_or_404(BenchmarkSuite, pk=pk)
    provider_id = request.POST.get('provider')
    model_name = request.POST.get('model_name', '').strip()
    num_questions = int(request.POST.get('num_questions_per_benchmark', 0) or 0)
    temperature = float(request.POST.get('temperature', 0.0) or 0.0)
    max_tokens = int(request.POST.get('max_tokens', 512) or 512)
    system_prompt = request.POST.get('system_prompt', '').strip()
    parallel_workers = int(request.POST.get('parallel_workers', 1) or 1)
    worker_mode = request.POST.get('worker_mode', 'shared')  # 'shared' | 'per_run'

    if not provider_id or not model_name:
        messages.error(request, 'Provider and model name are required.')
        return redirect('benchmarks:suite_detail', pk=pk)

    from apps.providers.models import Provider
    from apps.runs.models import BenchmarkSuiteRun, BenchmarkRun
    from apps.runs.runner import start_run_in_background

    try:
        provider = Provider.objects.get(id=provider_id)
    except Provider.DoesNotExist:
        messages.error(request, 'Invalid provider.')
        return redirect('benchmarks:suite_detail', pk=pk)

    suite_run = BenchmarkSuiteRun.objects.create(
        suite=suite,
        provider=provider,
        model_name=model_name,
        status='running',
        num_questions_per_benchmark=num_questions,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
    )

    items = list(suite.items.select_related('benchmark').all())

    def _run_suite():
        runs_created = []
        for item in items:
            run = BenchmarkRun.objects.create(
                benchmark=item.benchmark,
                provider=provider,
                model_name=model_name,
                num_questions=num_questions,
                temperature=temperature,
                max_tokens=max_tokens,
                parallel_workers=parallel_workers,
                system_prompt=system_prompt,
                suite_run=suite_run,
            )
            runs_created.append(run)

        if worker_mode == 'per_run':
            # One benchmark at a time, each using all parallel_workers internally
            run_ser = threading.Semaphore(1)
            threads = [
                start_run_in_background(run.id, run_serializer=run_ser)
                for run in runs_created
            ]
        else:
            # All benchmarks share the worker pool
            shared_sem = threading.Semaphore(parallel_workers)
            threads = [
                start_run_in_background(run.id, shared_semaphore=shared_sem)
                for run in runs_created
            ]

        # Wait for all benchmarks to finish before updating suite status
        for t in threads:
            t.join()

        from apps.runs.models import BenchmarkSuiteRun as SR
        sr = SR.objects.get(id=suite_run.id)
        all_runs = sr.benchmark_runs.all()
        if all_runs.filter(status='failed').exists():
            sr.status = 'failed'
        else:
            sr.status = 'completed'
        sr.completed_at = timezone.now()
        sr.save()

    threading.Thread(target=_run_suite, daemon=True).start()

    messages.success(
        request,
        f'Started suite run for "{suite.name}" with {model_name}. '
        f'Running {len(items)} benchmarks with {parallel_workers} parallel worker(s).'
    )
    return redirect('runs:suite_run_detail', pk=suite_run.pk)
