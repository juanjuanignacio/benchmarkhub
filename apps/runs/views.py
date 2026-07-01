import csv
import logging
import math
import threading
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Avg, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView

from apps.benchmarks.models import Benchmark
from apps.providers.models import Provider
from .models import BenchmarkRun, BenchmarkSuiteRun, RunResult, RunTemplate, ScheduledRun
from .runner import cancel_run, start_run_in_background

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _wilson_ci(correct: int, total: int, confidence: float = 0.95) -> tuple:
    """
    Wilson score confidence interval for a proportion.

    More accurate than the normal approximation, especially for small n or
    proportions near 0/1.  Returns (lower_pct, upper_pct) as percentages.

    Args:
        correct: number of successes
        total:   number of trials
        confidence: desired confidence level (default 95%)

    Returns:
        (lower, upper) as floats in [0, 100], or (None, None) if total == 0.
    """
    if total == 0:
        return None, None
    # z for the given confidence level via inverse normal CDF approximation
    # z=1.96 for 95%, z=1.645 for 90%, z=2.576 for 99%
    z_map = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}
    z = z_map.get(confidence, 1.960)
    p_hat = correct / total
    z2 = z * z
    denom = 1 + z2 / total
    centre = (p_hat + z2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / total + z2 / (4 * total * total))
    lower = max(0.0, (centre - margin) * 100)
    upper = min(100.0, (centre + margin) * 100)
    return round(lower, 1), round(upper, 1)


class RunListView(ListView):
    model = BenchmarkRun
    template_name = 'runs/list.html'
    context_object_name = 'runs'
    paginate_by = 20

    def get_queryset(self):
        qs = BenchmarkRun.objects.select_related('benchmark', 'provider').all()
        benchmark_id = self.request.GET.get('benchmark')
        provider_id = self.request.GET.get('provider')
        status = self.request.GET.get('status')
        tag = self.request.GET.get('tag', '').strip()

        if benchmark_id:
            qs = qs.filter(benchmark_id=benchmark_id)
        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        if status:
            qs = qs.filter(status=status)
        if tag:
            qs = qs.filter(tags__icontains=tag)

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['benchmarks'] = Benchmark.objects.filter(loaded_at__isnull=False)
        ctx['providers'] = Provider.objects.filter(is_active=True)
        ctx['status_choices'] = BenchmarkRun.STATUS_CHOICES
        ctx['filter_benchmark'] = self.request.GET.get('benchmark', '')
        ctx['filter_provider'] = self.request.GET.get('provider', '')
        ctx['filter_status'] = self.request.GET.get('status', '')
        ctx['filter_tag'] = self.request.GET.get('tag', '')
        return ctx


class RunCreateView(ListView):
    """Create and start a new benchmark run."""
    template_name = 'runs/create.html'
    model = Benchmark
    context_object_name = 'benchmarks'

    def get_queryset(self):
        return Benchmark.objects.filter(loaded_at__isnull=False, is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['providers'] = Provider.objects.filter(is_active=True)
        ctx['run_templates'] = list(RunTemplate.objects.values('pk', 'name', 'description', 'model_name', 'temperature', 'max_tokens', 'num_questions'))
        return ctx

    def post(self, request, *args, **kwargs):
        benchmark_id = request.POST.get('benchmark')
        provider_id = request.POST.get('provider')
        model_name = request.POST.get('model_name', '').strip()
        temperature = float(request.POST.get('temperature', 0.0) or 0.0)
        max_tokens = int(request.POST.get('max_tokens', 512) or 512)
        num_questions = int(request.POST.get('num_questions', 0) or 0)
        system_prompt = request.POST.get('system_prompt', '').strip()
        notes = request.POST.get('notes', '').strip()
        tags = request.POST.get('tags', '').strip()
        parallel_workers = int(request.POST.get('parallel_workers', 1) or 1)
        few_shot_count = int(request.POST.get('few_shot_count', 0) or 0)
        use_cot = request.POST.get('use_cot', '') == 'on'
        webhook_url = request.POST.get('webhook_url', '').strip()

        if not benchmark_id or not provider_id or not model_name:
            messages.error(request, 'Please fill in all required fields.')
            return redirect('runs:create')

        try:
            benchmark = Benchmark.objects.get(id=benchmark_id)
            provider = Provider.objects.get(id=provider_id)
        except (Benchmark.DoesNotExist, Provider.DoesNotExist):
            messages.error(request, 'Invalid benchmark or provider.')
            return redirect('runs:create')

        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            provider=provider,
            model_name=model_name,
            status='pending',
            num_questions=num_questions,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            notes=notes,
            tags=tags,
            parallel_workers=max(1, parallel_workers),
            few_shot_count=max(0, few_shot_count),
            use_cot=use_cot,
            webhook_url=webhook_url,
        )

        # Start background thread
        start_run_in_background(run.id)

        messages.success(
            request,
            f'Started benchmark run: {benchmark.name} with {model_name}. '
            f'Running {"all" if num_questions == 0 else num_questions} questions.'
        )
        return redirect('runs:detail', pk=run.pk)


class RunDetailView(DetailView):
    model = BenchmarkRun
    template_name = 'runs/detail.html'
    context_object_name = 'run'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        run = self.object

        # Recent results (sample)
        results_qs = run.results.select_related('question').order_by('-created_at')
        paginator = Paginator(results_qs, 20)
        page_number = self.request.GET.get('page', 1)
        ctx['results_page'] = paginator.get_page(page_number)

        # Stats by subject
        subject_stats = []
        subjects = (
            run.results.filter(question__subject__isnull=False)
            .exclude(question__subject='')
            .values('question__subject')
            .annotate(
                total=Count('id'),
                correct=Count('id', filter=Q(is_correct=True)),
            )
            .order_by('-total')[:15]
        )
        for s in subjects:
            total = s['total']
            correct = s['correct']
            pct = round(correct / total * 100, 1) if total > 0 else 0
            subject_stats.append({
                'subject': s['question__subject'],
                'total': total,
                'correct': correct,
                'pct': pct,
            })
        ctx['subject_stats'] = subject_stats

        # Filter
        result_filter = self.request.GET.get('filter', 'all')
        ctx['result_filter'] = result_filter
        ctx['answered_count'] = run.results.count()

        # Tags as list
        if run.tags:
            ctx['tags_list'] = [t.strip() for t in run.tags.split(',') if t.strip()]
        else:
            ctx['tags_list'] = []

        # Token & cost stats
        token_stats = run.results.aggregate(
            total_input=Sum('tokens_input'),
            total_output=Sum('tokens_output'),
            total_cost=Sum('estimated_cost'),
            avg_time=Avg('response_time'),
        )
        ctx['token_stats'] = token_stats

        # Check for failed results
        ctx['failed_count'] = run.results.filter(
            Q(error_message__isnull=False) & ~Q(error_message='')
        ).count()

        # 95% Wilson confidence interval for the overall score
        ci_low, ci_high = _wilson_ci(run.correct_answers, run.total_questions)
        ctx['ci_low'] = ci_low
        ctx['ci_high'] = ci_high

        # Add per-subject CIs
        for s in subject_stats:
            s['ci_low'], s['ci_high'] = _wilson_ci(s['correct'], s['total'])

        return ctx

    def post(self, request, *args, **kwargs):
        """Handle inline notes/tags update."""
        run = get_object_or_404(BenchmarkRun, pk=self.kwargs['pk'])
        action = request.POST.get('action', '')
        if action == 'update_notes_tags':
            run.notes = request.POST.get('notes', '').strip()
            run.tags = request.POST.get('tags', '').strip()
            run.save(update_fields=['notes', 'tags'])
            messages.success(request, 'Notes and tags updated.')
        return redirect('runs:detail', pk=run.pk)


class RunResultsView(ListView):
    template_name = 'runs/results.html'
    context_object_name = 'results'
    paginate_by = 20

    def get_queryset(self):
        self.run = get_object_or_404(BenchmarkRun, pk=self.kwargs['pk'])
        qs = RunResult.objects.filter(run=self.run).select_related('question')
        result_filter = self.request.GET.get('filter', 'all')
        if result_filter == 'correct':
            qs = qs.filter(is_correct=True)
        elif result_filter == 'incorrect':
            qs = qs.filter(is_correct=False)
        return qs.order_by('created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['run'] = self.run
        ctx['result_filter'] = self.request.GET.get('filter', 'all')
        ctx['total_count'] = self.run.results.count()
        ctx['correct_count'] = self.run.results.filter(is_correct=True).count()
        ctx['incorrect_count'] = self.run.results.filter(is_correct=False).count()
        return ctx


def delete_run_view(request, pk):
    if request.method != 'POST':
        return redirect('runs:list')
    run = get_object_or_404(BenchmarkRun, pk=pk)
    run_name = str(run)
    # Stop the background thread before deleting so the runner does not keep
    # sending requests to the provider after the DB record is gone.
    if run.status in ('pending', 'running'):
        cancel_run(run.pk)
    run.delete()
    messages.success(request, f'Run "{run_name}" deleted.')
    return redirect('runs:list')


def cancel_run_view(request, pk):
    if request.method != 'POST':
        return redirect('runs:detail', pk=pk)
    success = cancel_run(pk)
    if success:
        messages.success(request, 'Run cancelled.')
    else:
        messages.warning(request, 'Could not cancel run (may already be completed).')
    return redirect('runs:detail', pk=pk)


def run_status_api(request, pk):
    """AJAX endpoint returning run status as JSON."""
    run = get_object_or_404(BenchmarkRun, pk=pk)
    answered = run.results.count()
    return JsonResponse({
        'status': run.status,
        'score': round(run.score, 2),
        'total_questions': run.total_questions,
        'correct_answers': run.correct_answers,
        'answered_count': answered,
        'progress_pct': run.progress_pct,
        'duration_seconds': run.duration_seconds,
        'error_message': run.error_message,
    })


def export_run_csv(request, pk):
    run = get_object_or_404(BenchmarkRun, pk=pk)
    results = RunResult.objects.filter(run=run).select_related('question').order_by('created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="run_{pk}_results.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'question_id', 'question', 'correct_answer', 'model_response',
        'parsed_answer', 'is_correct', 'response_time', 'subject', 'difficulty',
        'tokens_input', 'tokens_output', 'estimated_cost'
    ])
    for r in results:
        writer.writerow([
            r.question.question_id,
            r.question.question[:200],
            r.question.correct_answer,
            r.model_response[:200],
            r.parsed_answer,
            'yes' if r.is_correct else 'no',
            f"{r.response_time:.3f}",
            r.question.subject,
            r.question.difficulty,
            r.tokens_input,
            r.tokens_output,
            f"{r.estimated_cost:.6f}",
        ])
    return response


def export_run_excel(request, pk):
    run = get_object_or_404(BenchmarkRun, pk=pk)
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        messages.error(request, 'openpyxl is not installed. Please install it with: pip install openpyxl')
        return redirect('runs:detail', pk=pk)

    wb = openpyxl.Workbook()

    # Sheet 1: Summary
    ws_summary = wb.active
    ws_summary.title = 'Summary'
    summary_data = [
        ('Run ID', run.id),
        ('Benchmark', run.benchmark.name),
        ('Provider', run.provider.name),
        ('Model', run.model_name),
        ('Status', run.status),
        ('Score', f"{run.score:.1f}%"),
        ('Correct Answers', run.correct_answers),
        ('Total Questions', run.total_questions),
        ('Temperature', run.temperature),
        ('Max Tokens', run.max_tokens),
        ('Created At', str(run.created_at)),
        ('Started At', str(run.started_at or '-')),
        ('Completed At', str(run.completed_at or '-')),
        ('Duration (s)', str(run.duration_seconds or '-')),
        ('Notes', run.notes),
        ('Tags', run.tags),
    ]
    for row_idx, (label, value) in enumerate(summary_data, 1):
        ws_summary.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
        ws_summary.cell(row=row_idx, column=2, value=value)

    # Sheet 2: By Subject
    ws_subject = wb.create_sheet('By Subject')
    subject_headers = ['Subject', 'Correct', 'Total', 'Score %']
    for col, h in enumerate(subject_headers, 1):
        ws_subject.cell(row=1, column=col, value=h).font = Font(bold=True)

    subjects = (
        run.results.filter(question__subject__isnull=False)
        .exclude(question__subject='')
        .values('question__subject')
        .annotate(total=Count('id'), correct=Count('id', filter=Q(is_correct=True)))
        .order_by('-total')
    )
    for row_idx, s in enumerate(subjects, 2):
        total = s['total']
        correct = s['correct']
        pct = round(correct / total * 100, 1) if total > 0 else 0
        ws_subject.cell(row=row_idx, column=1, value=s['question__subject'])
        ws_subject.cell(row=row_idx, column=2, value=correct)
        ws_subject.cell(row=row_idx, column=3, value=total)
        ws_subject.cell(row=row_idx, column=4, value=pct)

    # Sheet 3: Results
    ws_results = wb.create_sheet('Results')
    result_headers = [
        'Question ID', 'Question', 'Correct Answer', 'Model Response',
        'Parsed Answer', 'Is Correct', 'Response Time (s)',
        'Tokens Input', 'Tokens Output', 'Est. Cost', 'Subject', 'Difficulty'
    ]
    for col, h in enumerate(result_headers, 1):
        ws_results.cell(row=1, column=col, value=h).font = Font(bold=True)

    results = RunResult.objects.filter(run=run).select_related('question').order_by('created_at')
    for row_idx, r in enumerate(results, 2):
        ws_results.cell(row=row_idx, column=1, value=r.question.question_id)
        ws_results.cell(row=row_idx, column=2, value=r.question.question[:300])
        ws_results.cell(row=row_idx, column=3, value=r.question.correct_answer)
        ws_results.cell(row=row_idx, column=4, value=r.model_response[:300])
        ws_results.cell(row=row_idx, column=5, value=r.parsed_answer)
        ws_results.cell(row=row_idx, column=6, value='Yes' if r.is_correct else 'No')
        ws_results.cell(row=row_idx, column=7, value=round(r.response_time, 3))
        ws_results.cell(row=row_idx, column=8, value=r.tokens_input)
        ws_results.cell(row=row_idx, column=9, value=r.tokens_output)
        ws_results.cell(row=row_idx, column=10, value=round(r.estimated_cost, 6))
        ws_results.cell(row=row_idx, column=11, value=r.question.subject)
        ws_results.cell(row=row_idx, column=12, value=r.question.difficulty)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="run_{pk}_results.xlsx"'
    wb.save(response)
    return response


def compare_view(request):
    """Compare multiple runs side by side (same benchmark only)."""
    run_ids_str = request.GET.get('runs', '')
    selected_run_ids = []
    if run_ids_str:
        for part in run_ids_str.split(','):
            part = part.strip()
            if part.isdigit():
                selected_run_ids.append(int(part))
    selected_run_ids = selected_run_ids[:4]

    runs = []
    if selected_run_ids:
        runs = list(
            BenchmarkRun.objects.filter(
                pk__in=selected_run_ids, status='completed'
            ).select_related('benchmark', 'provider')
        )
        runs.sort(key=lambda r: selected_run_ids.index(r.pk) if r.pk in selected_run_ids else 999)

    # Warn if runs come from different benchmarks
    different_benchmarks = len({r.benchmark_id for r in runs}) > 1

    # Per-subject accuracy for each run
    subjects_set = set()
    run_subject_map = {}  # run.pk -> {subject: {total, correct, pct}}

    for run in runs:
        subject_data = {}
        subject_qs = (
            run.results.filter(question__subject__isnull=False)
            .exclude(question__subject='')
            .values('question__subject')
            .annotate(
                total=Count('id'),
                correct=Count('id', filter=Q(is_correct=True)),
            )
        )
        for s in subject_qs:
            subj = s['question__subject']
            subjects_set.add(subj)
            total = s['total']
            correct = s['correct']
            subject_data[subj] = {
                'total': total,
                'correct': correct,
                'pct': round(correct / total * 100, 1) if total > 0 else 0.0,
            }
        run_subject_map[run.pk] = subject_data

    subjects = sorted(subjects_set)

    # Build template-friendly table rows: list of (subject, [cell, cell, ...])
    # where each cell = {'pct': float, 'correct': int, 'total': int} or None
    subject_rows = []
    for subj in subjects:
        cells = []
        for run in runs:
            cells.append(run_subject_map[run.pk].get(subj))
        subject_rows.append({'subject': subj, 'cells': cells})

    # Build chart data (JSON-safe, indexed by run position)
    import json
    chart_subjects = subjects
    chart_datasets = []
    colors = ['#0d6efd', '#198754', '#ffc107', '#dc3545']
    for i, run in enumerate(runs):
        sd = run_subject_map[run.pk]
        chart_datasets.append({
            'label': f'Run #{run.pk} — {run.model_name[:20]}',
            'data': [sd.get(s, {}).get('pct', 0) for s in chart_subjects],
            'backgroundColor': colors[i % len(colors)],
        })

    # Question-level differences (same-benchmark runs only)
    question_diffs = []
    if len(runs) >= 2 and not different_benchmarks:
        first_run = runs[0]
        first_results = {
            r.question_id: r
            for r in RunResult.objects.filter(run=first_run).select_related('question')
        }
        other_results = {}
        for run in runs[1:]:
            other_results[run.pk] = {
                r.question_id: r
                for r in RunResult.objects.filter(run=run).select_related('question')
            }

        for qid, first_result in list(first_results.items())[:500]:
            disagreement = any(
                (other_results.get(run.pk, {}).get(qid) and
                 other_results[run.pk][qid].is_correct != first_result.is_correct)
                for run in runs[1:]
            )
            if disagreement:
                row = {'question': first_result.question, 'results': {first_run.pk: first_result}}
                for run in runs[1:]:
                    row['results'][run.pk] = other_results.get(run.pk, {}).get(qid)
                question_diffs.append(row)
                if len(question_diffs) >= 50:
                    break

    # All completed runs grouped by benchmark for the selector
    all_completed_runs = (
        BenchmarkRun.objects.filter(status='completed')
        .select_related('benchmark', 'provider')
        .order_by('benchmark__name', '-score')[:200]
    )

    return render(request, 'runs/compare.html', {
        'runs': runs,
        'subjects': subjects,
        'subject_rows': subject_rows,
        'chart_subjects_json': json.dumps(chart_subjects),
        'chart_datasets_json': json.dumps(chart_datasets),
        'question_diffs': question_diffs,
        'all_completed_runs': all_completed_runs,
        'selected_run_ids': selected_run_ids,
        'runs_param': run_ids_str,
        'different_benchmarks': different_benchmarks,
    })


def retry_failed_view(request, pk):
    if request.method != 'POST':
        return redirect('runs:detail', pk=pk)

    original_run = get_object_or_404(BenchmarkRun, pk=pk)

    # Find failed results
    failed_results = original_run.results.filter(
        Q(error_message__isnull=False, error_message__gt='') | Q(is_correct__isnull=True)
    )

    if not failed_results.exists():
        messages.warning(request, 'No failed questions found to retry.')
        return redirect('runs:detail', pk=pk)

    failed_question_ids = list(failed_results.values_list('question__question_id', flat=True))

    new_run = BenchmarkRun.objects.create(
        benchmark=original_run.benchmark,
        provider=original_run.provider,
        model_name=original_run.model_name,
        status='pending',
        num_questions=original_run.num_questions,
        system_prompt=original_run.system_prompt,
        temperature=original_run.temperature,
        max_tokens=original_run.max_tokens,
        notes=f"Retry of run #{original_run.pk}",
        tags=original_run.tags,
        parallel_workers=original_run.parallel_workers,
        few_shot_count=original_run.few_shot_count,
        use_cot=original_run.use_cot,
        webhook_url=original_run.webhook_url,
        metadata={'retry_question_ids': failed_question_ids, 'original_run_id': original_run.pk},
    )

    start_run_in_background(new_run.id)

    messages.success(
        request,
        f'Started retry run #{new_run.pk} with {len(failed_question_ids)} failed questions.'
    )
    return redirect('runs:detail', pk=new_run.pk)


def estimate_cost_view(request):
    """Cost estimation page + AJAX endpoint."""
    from .cost_table import estimate_run_cost, MODEL_COSTS

    # If AJAX request (has model param), return JSON
    model_name = request.GET.get('model', '').strip()
    if model_name and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        benchmark_id = request.GET.get('benchmark_id', '')
        num_questions = int(request.GET.get('num_questions', 0) or 0)
        if benchmark_id and num_questions == 0:
            try:
                b = Benchmark.objects.get(id=benchmark_id)
                num_questions = b.num_questions
            except Benchmark.DoesNotExist:
                pass
        if num_questions == 0:
            num_questions = 100
        estimated = estimate_run_cost(model_name, num_questions)
        tokens_estimate = num_questions * (150 + 50)
        return JsonResponse({
            'estimated_cost': round(estimated, 4),
            'currency': 'USD',
            'tokens_estimate': tokens_estimate,
            'num_questions': num_questions,
            'model': model_name,
        })

    # Full page: show cost calculator
    benchmarks = Benchmark.objects.filter(is_active=True).order_by('name')
    known_models = [k for k in MODEL_COSTS.keys() if k != 'default']

    # Pre-calculate cost estimates for all model/benchmark combos if params given
    result = None
    if model_name:
        benchmark_id = request.GET.get('benchmark_id', '')
        num_questions = int(request.GET.get('num_questions', 0) or 0)
        if benchmark_id:
            try:
                b = Benchmark.objects.get(id=benchmark_id)
                if num_questions == 0:
                    num_questions = b.num_questions
            except Benchmark.DoesNotExist:
                pass
        if num_questions == 0:
            num_questions = 100
        estimated = estimate_run_cost(model_name, num_questions)
        from .cost_table import get_model_cost
        cost_in, cost_out = get_model_cost(model_name)

        # Time estimation: use average response time from previous runs with this model
        avg_resp = RunResult.objects.filter(
            run__model_name__icontains=model_name,
            response_time__gt=0,
        ).aggregate(avg=Avg('response_time'))['avg']
        estimated_seconds = None
        estimated_time_display = None
        if avg_resp:
            estimated_seconds = int(avg_resp * num_questions)
            if estimated_seconds < 60:
                estimated_time_display = f"{estimated_seconds}s"
            elif estimated_seconds < 3600:
                m, s = divmod(estimated_seconds, 60)
                estimated_time_display = f"{m}m {s}s"
            else:
                h, rem = divmod(estimated_seconds, 3600)
                m = rem // 60
                estimated_time_display = f"{h}h {m}m"

        result = {
            'model': model_name,
            'num_questions': num_questions,
            'estimated_cost': round(estimated, 4),
            'tokens_estimate': num_questions * 200,
            'cost_per_1k_input': cost_in,
            'cost_per_1k_output': cost_out,
            'estimated_time': estimated_time_display,
            'avg_response_time': round(avg_resp, 2) if avg_resp else None,
        }

    return render(request, 'runs/estimate_cost.html', {
        'benchmarks': benchmarks,
        'known_models': known_models,
        'result': result,
        'selected_model': model_name,
        'selected_benchmark': request.GET.get('benchmark_id', ''),
        'selected_questions': request.GET.get('num_questions', ''),
    })


def ab_test_view(request):
    benchmarks = Benchmark.objects.filter(loaded_at__isnull=False, is_active=True)
    providers = Provider.objects.filter(is_active=True)

    if request.method == 'GET':
        return render(request, 'runs/ab_test.html', {
            'benchmarks': benchmarks,
            'providers': providers,
        })

    benchmark_id = request.POST.get('benchmark')
    provider_id = request.POST.get('provider')
    model_name = request.POST.get('model_name', '').strip()
    num_questions = int(request.POST.get('num_questions', 0) or 0)
    system_prompt_a = request.POST.get('system_prompt_a', '').strip()
    system_prompt_b = request.POST.get('system_prompt_b', '').strip()
    name_a = request.POST.get('name_a', 'Variant A').strip()
    name_b = request.POST.get('name_b', 'Variant B').strip()
    temperature = float(request.POST.get('temperature', 0.0) or 0.0)
    max_tokens = int(request.POST.get('max_tokens', 512) or 512)

    if not benchmark_id or not provider_id or not model_name:
        messages.error(request, 'Benchmark, provider, and model name are required.')
        return render(request, 'runs/ab_test.html', {
            'benchmarks': benchmarks,
            'providers': providers,
        })

    try:
        benchmark = Benchmark.objects.get(id=benchmark_id)
        provider = Provider.objects.get(id=provider_id)
    except (Benchmark.DoesNotExist, Provider.DoesNotExist):
        messages.error(request, 'Invalid benchmark or provider.')
        return render(request, 'runs/ab_test.html', {
            'benchmarks': benchmarks,
            'providers': providers,
        })

    ab_test_id = str(uuid.uuid4())[:8]

    run_a = BenchmarkRun.objects.create(
        benchmark=benchmark,
        provider=provider,
        model_name=model_name,
        num_questions=num_questions,
        system_prompt=system_prompt_a,
        temperature=temperature,
        max_tokens=max_tokens,
        tags=f"ab_test,variant_a,{name_a}",
        notes=f"A/B Test {ab_test_id} - {name_a}",
        metadata={'ab_test_id': ab_test_id, 'ab_variant': 'A', 'ab_name': name_a},
    )
    run_b = BenchmarkRun.objects.create(
        benchmark=benchmark,
        provider=provider,
        model_name=model_name,
        num_questions=num_questions,
        system_prompt=system_prompt_b,
        temperature=temperature,
        max_tokens=max_tokens,
        tags=f"ab_test,variant_b,{name_b}",
        notes=f"A/B Test {ab_test_id} - {name_b}",
        metadata={'ab_test_id': ab_test_id, 'ab_variant': 'B', 'ab_name': name_b},
    )

    start_run_in_background(run_a.id)
    start_run_in_background(run_b.id)

    messages.success(request, f'A/B test started! Run A: #{run_a.pk}, Run B: #{run_b.pk}')
    return redirect('runs:ab_results', ab_test_id=ab_test_id)


def _mcnemar_test(results_a, results_b):
    """
    McNemar's test for paired dichotomous data with continuity correction.

    Args:
        results_a, results_b: lists of (question_id, is_correct) tuples

    Returns:
        (chi_square, p_value, significant)

    The p-value uses the exact chi-squared(df=1) survival function via
    math.erfc (Python stdlib, no scipy needed):
        P(chi2(df=1) > x) = erfc(sqrt(x / 2))
    This replaces the previous approximation exp(-chi2/2), which could
    be off by up to 30% near typical significance thresholds.
    """
    a_dict = {qa: ca for qa, ca in results_a}
    b_dict = {qb: cb for qb, cb in results_b}

    common_ids = set(a_dict.keys()) & set(b_dict.keys())
    b_count = sum(1 for qid in common_ids if a_dict[qid] and not b_dict[qid])
    c_count = sum(1 for qid in common_ids if not a_dict[qid] and b_dict[qid])

    if b_count + c_count == 0:
        return 0, 1.0, False

    # McNemar chi-square with continuity correction (Edwards, 1948)
    chi2_val = (abs(b_count - c_count) - 1) ** 2 / (b_count + c_count)
    # Exact p-value: P(chi2(df=1) > x) = erfc(sqrt(x/2))
    p = math.erfc(math.sqrt(chi2_val / 2))
    return chi2_val, p, p < 0.05


def ab_results_view(request, ab_test_id):
    runs = BenchmarkRun.objects.filter(
        metadata__ab_test_id=ab_test_id
    ).select_related('benchmark', 'provider').order_by('created_at')

    if not runs.exists():
        messages.error(request, f'No A/B test found with ID: {ab_test_id}')
        return redirect('runs:list')

    run_a = runs.filter(metadata__ab_variant='A').first()
    run_b = runs.filter(metadata__ab_variant='B').first()

    # Subject comparison
    def get_subject_data(run):
        if not run:
            return {}
        subjects = (
            run.results.filter(question__subject__isnull=False)
            .exclude(question__subject='')
            .values('question__subject')
            .annotate(total=Count('id'), correct=Count('id', filter=Q(is_correct=True)))
            .order_by('-total')
        )
        return {
            s['question__subject']: {
                'total': s['total'],
                'correct': s['correct'],
                'pct': round(s['correct'] / s['total'] * 100, 1) if s['total'] > 0 else 0
            }
            for s in subjects
        }

    subject_data_a = get_subject_data(run_a)
    subject_data_b = get_subject_data(run_b)
    all_subjects = sorted(set(list(subject_data_a.keys()) + list(subject_data_b.keys())))

    # Question-level differences
    question_diffs = []
    chi2 = p_value = 0
    significant = False

    if run_a and run_b:
        results_a_qs = RunResult.objects.filter(run=run_a).select_related('question')
        results_b_qs = RunResult.objects.filter(run=run_b).select_related('question')

        a_map = {r.question.question_id: r for r in results_a_qs}
        b_map = {r.question.question_id: r for r in results_b_qs}
        common_qids = set(a_map.keys()) & set(b_map.keys())

        for qid in list(common_qids)[:100]:
            ra = a_map[qid]
            rb = b_map[qid]
            if ra.is_correct != rb.is_correct:
                question_diffs.append({
                    'question': ra.question,
                    'result_a': ra,
                    'result_b': rb,
                })

        # McNemar's test
        results_a_list = [(qid, a_map[qid].is_correct) for qid in common_qids]
        results_b_list = [(qid, b_map[qid].is_correct) for qid in common_qids]
        chi2, p_value, significant = _mcnemar_test(results_a_list, results_b_list)

    return render(request, 'runs/ab_results.html', {
        'ab_test_id': ab_test_id,
        'run_a': run_a,
        'run_b': run_b,
        'subject_data_a': subject_data_a,
        'subject_data_b': subject_data_b,
        'all_subjects': all_subjects,
        'question_diffs': question_diffs[:50],
        'chi2': round(chi2, 4),
        'p_value': round(p_value, 4),
        'significant': significant,
    })


def model_history_view(request):
    model_name = request.GET.get('model_name', '').strip()
    benchmarks_data = {}

    if model_name:
        runs = (
            BenchmarkRun.objects.filter(
                status='completed', model_name__icontains=model_name
            )
            .select_related('benchmark')
            .order_by('benchmark__name', 'created_at')
        )

        for run in runs:
            bench_name = run.benchmark.name
            if bench_name not in benchmarks_data:
                benchmarks_data[bench_name] = []
            benchmarks_data[bench_name].append({
                'date': run.created_at.isoformat(),
                'date_display': run.created_at.strftime('%Y-%m-%d'),
                'score': round(run.score, 2),
                'run_id': run.pk,
            })

    return render(request, 'runs/model_history.html', {
        'model_name': model_name,
        'benchmarks_data': benchmarks_data,
        'has_data': bool(benchmarks_data),
    })


def suite_run_detail_view(request, pk):
    suite_run = get_object_or_404(BenchmarkSuiteRun, pk=pk)
    benchmark_runs = suite_run.benchmark_runs.select_related('benchmark', 'provider').order_by('created_at')
    done, total = suite_run.progress
    return render(request, 'runs/suite_run_detail.html', {
        'suite_run': suite_run,
        'benchmark_runs': benchmark_runs,
        'done': done,
        'total': total,
        'progress_pct': round(done / total * 100, 1) if total > 0 else 0,
    })


def scheduled_list_view(request):
    scheduled = ScheduledRun.objects.select_related('benchmark', 'provider', 'last_run').all()
    return render(request, 'runs/scheduled.html', {'scheduled_runs': scheduled})


def scheduled_create_view(request):
    benchmarks = Benchmark.objects.filter(loaded_at__isnull=False, is_active=True)
    providers = Provider.objects.filter(is_active=True)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        benchmark_id = request.POST.get('benchmark')
        provider_id = request.POST.get('provider')
        model_name = request.POST.get('model_name', '').strip()
        num_questions = int(request.POST.get('num_questions', 0) or 0)
        system_prompt = request.POST.get('system_prompt', '').strip()
        temperature = float(request.POST.get('temperature', 0.0) or 0.0)
        max_tokens = int(request.POST.get('max_tokens', 512) or 512)
        run_at_str = request.POST.get('run_at', '').strip()
        frequency = request.POST.get('frequency', 'once')

        if not name or not benchmark_id or not provider_id or not model_name or not run_at_str:
            messages.error(request, 'All required fields must be filled in.')
            return render(request, 'runs/scheduled_create.html', {
                'benchmarks': benchmarks,
                'providers': providers,
            })

        try:
            benchmark = Benchmark.objects.get(id=benchmark_id)
            provider = Provider.objects.get(id=provider_id)
        except (Benchmark.DoesNotExist, Provider.DoesNotExist):
            messages.error(request, 'Invalid benchmark or provider.')
            return render(request, 'runs/scheduled_create.html', {
                'benchmarks': benchmarks,
                'providers': providers,
            })

        try:
            from django.utils.dateparse import parse_datetime
            run_at = parse_datetime(run_at_str)
            if run_at is None:
                raise ValueError("Invalid datetime format")
            if timezone.is_naive(run_at):
                run_at = timezone.make_aware(run_at)
        except Exception:
            messages.error(request, 'Invalid date/time format. Use YYYY-MM-DDTHH:MM format.')
            return render(request, 'runs/scheduled_create.html', {
                'benchmarks': benchmarks,
                'providers': providers,
            })

        sr = ScheduledRun.objects.create(
            name=name,
            benchmark=benchmark,
            provider=provider,
            model_name=model_name,
            num_questions=num_questions,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            run_at=run_at,
            frequency=frequency,
        )
        messages.success(request, f'Scheduled run "{name}" created.')
        return redirect('runs:scheduled_list')

    return render(request, 'runs/scheduled_create.html', {
        'benchmarks': benchmarks,
        'providers': providers,
    })


def scheduled_delete_view(request, pk):
    sr = get_object_or_404(ScheduledRun, pk=pk)
    if request.method == 'POST':
        name = sr.name
        sr.delete()
        messages.success(request, f'Scheduled run "{name}" deleted.')
    return redirect('runs:scheduled_list')


def scheduled_toggle_view(request, pk):
    if request.method != 'POST':
        return redirect('runs:scheduled_list')
    sr = get_object_or_404(ScheduledRun, pk=pk)
    sr.is_active = not sr.is_active
    sr.save(update_fields=['is_active'])
    status_msg = 'enabled' if sr.is_active else 'paused'
    messages.success(request, f'Scheduled run "{sr.name}" {status_msg}.')
    return redirect('runs:scheduled_list')


def import_csv_view(request):
    """Import answered CSV from the Runs section (not tied to a specific benchmark page)."""
    import csv
    import io
    import threading
    from django.utils.safestring import mark_safe
    from apps.benchmarks.views import _run_csv_import_background

    benchmarks = Benchmark.objects.filter(loaded_at__isnull=False, is_active=True)

    if request.method == 'GET':
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    benchmark_id = request.POST.get('benchmark', '').strip()
    model_name = request.POST.get('model_name', '').strip() or 'CSV / Manual Import'
    csv_file = request.FILES.get('csv_file')
    tags = request.POST.get('tags', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not benchmark_id or not csv_file:
        messages.error(request, 'Benchmark and CSV file are required.')
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    try:
        benchmark = Benchmark.objects.get(pk=benchmark_id)
    except Benchmark.DoesNotExist:
        messages.error(request, 'Invalid benchmark selected.')
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    # Read CSV content before the thread starts
    try:
        csv_content = csv_file.read().decode('utf-8-sig')
    except Exception as e:
        messages.error(request, f'Could not read CSV file: {e}')
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    # Validate required columns before creating any DB records
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        columns = reader.fieldnames or []
        required = {'question_id', 'answer'}
        missing = required - {c.strip().lower() for c in columns}
        if missing:
            missing_str = ', '.join(f'<code>{c}</code>' for c in sorted(missing))
            found_str = ', '.join(f'<code>{c}</code>' for c in columns) if columns else '(none detected)'
            messages.error(request, mark_safe(
                f'Missing required column(s): {missing_str}. '
                f'Columns found in your CSV: {found_str}.'
            ))
            return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})
        if not columns:
            messages.error(request, 'The CSV file appears to be empty or has no header row.')
            return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})
    except Exception as e:
        messages.error(request, f'Could not parse CSV: {e}')
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    from apps.providers.models import Provider
    try:
        csv_provider, _ = Provider.objects.get_or_create(
            slug='csv-manual',
            defaults={'name': 'CSV / Manual', 'provider_type': 'custom', 'default_model': 'manual', 'is_active': True}
        )
    except Exception as e:
        messages.error(request, f'Could not create CSV provider: {e}')
        return render(request, 'runs/import_csv.html', {'benchmarks': benchmarks})

    is_rag = (benchmark.metadata or {}).get('is_rag', False)
    run = BenchmarkRun.objects.create(
        benchmark=benchmark,
        provider=csv_provider,
        model_name=model_name,
        status='running',
        started_at=timezone.now(),
        tags=tags or 'csv-import',
        notes=notes,
        metadata={'source': 'csv_import', 'is_rag': is_rag},
    )

    t = threading.Thread(
        target=_run_csv_import_background,
        args=(run.pk, benchmark.pk, benchmark.slug, csv_content),
        daemon=True,
    )
    t.start()

    messages.info(request, f'CSV import started for "{model_name}" — processing in the background.')
    return redirect('runs:detail', pk=run.pk)


# ---------------------------------------------------------------------------
# Run Templates
# ---------------------------------------------------------------------------

def template_list_view(request):
    """List saved run templates."""
    templates = RunTemplate.objects.all()
    return render(request, 'runs/template_list.html', {'templates': templates})


def template_create_view(request):
    """
    Create a new run template, optionally pre-filled from an existing run.
    GET ?from_run=<pk> pre-fills the form with that run's config.
    """
    initial = {}
    from_run_pk = request.GET.get('from_run')
    if from_run_pk:
        try:
            source = BenchmarkRun.objects.get(pk=from_run_pk)
            initial = {
                'model_name': source.model_name,
                'temperature': source.temperature,
                'max_tokens': source.max_tokens,
                'system_prompt': source.system_prompt,
                'num_questions': source.num_questions,
                'parallel_workers': source.parallel_workers,
                'few_shot_count': source.few_shot_count,
                'use_cot': source.use_cot,
                'description': f'From run #{source.pk} — {source.benchmark.name}',
            }
        except BenchmarkRun.DoesNotExist:
            pass

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Template name is required.')
            return redirect('runs:template_create')
        template = RunTemplate.objects.create(
            name=name,
            description=request.POST.get('description', '').strip(),
            model_name=request.POST.get('model_name', '').strip(),
            temperature=float(request.POST.get('temperature', 0.0) or 0.0),
            max_tokens=int(request.POST.get('max_tokens', 512) or 512),
            system_prompt=request.POST.get('system_prompt', '').strip(),
            num_questions=int(request.POST.get('num_questions', 0) or 0),
            parallel_workers=int(request.POST.get('parallel_workers', 1) or 1),
            few_shot_count=int(request.POST.get('few_shot_count', 0) or 0),
            use_cot=request.POST.get('use_cot', '') == 'on',
        )
        messages.success(request, f'Template "{template.name}" saved.')
        return redirect('runs:template_list')

    return render(request, 'runs/template_form.html', {'initial': initial, 'action': 'Create'})


def template_delete_view(request, pk):
    template = get_object_or_404(RunTemplate, pk=pk)
    if request.method == 'POST':
        name = template.name
        template.delete()
        messages.success(request, f'Template "{name}" deleted.')
    return redirect('runs:template_list')


def template_apply_api(request, pk):
    """Return template params as JSON (called by run-create page JS)."""
    template = get_object_or_404(RunTemplate, pk=pk)
    return JsonResponse(template.as_dict())


# ---------------------------------------------------------------------------
# Parameter Sweep
# ---------------------------------------------------------------------------

def parameter_sweep_view(request):
    """
    Run the same benchmark with a range of parameter values.

    Supports two sweep modes:
    - temperature sweep: comma-separated list of floats, e.g. "0.0, 0.5, 1.0"
    - prompt sweep: one system prompt per line (textarea)

    Each value creates one run tagged with 'sweep,sweep_<uid>'.
    """
    benchmarks = Benchmark.objects.filter(loaded_at__isnull=False, is_active=True).order_by('name')
    providers = Provider.objects.filter(is_active=True)

    if request.method == 'GET':
        return render(request, 'runs/parameter_sweep.html', {
            'benchmarks': benchmarks,
            'providers': providers,
        })

    benchmark_id = request.POST.get('benchmark')
    provider_id = request.POST.get('provider')
    model_name = request.POST.get('model_name', '').strip()
    sweep_type = request.POST.get('sweep_type', 'temperature')
    num_questions = int(request.POST.get('num_questions', 0) or 0)
    max_tokens = int(request.POST.get('max_tokens', 512) or 512)
    base_system_prompt = request.POST.get('base_system_prompt', '').strip()

    if not benchmark_id or not provider_id or not model_name:
        messages.error(request, 'Benchmark, provider and model name are required.')
        return redirect('runs:parameter_sweep')

    try:
        benchmark = Benchmark.objects.get(id=benchmark_id)
        provider = Provider.objects.get(id=provider_id)
    except (Benchmark.DoesNotExist, Provider.DoesNotExist):
        messages.error(request, 'Invalid benchmark or provider.')
        return redirect('runs:parameter_sweep')

    parallel_workers = int(request.POST.get('parallel_workers', 1) or 1)
    worker_mode = request.POST.get('worker_mode', 'shared')  # 'shared' | 'per_run'
    sweep_uid = str(uuid.uuid4())[:8]
    runs_created = []

    if sweep_type == 'temperature':
        raw = request.POST.get('temperatures', '0.0, 0.5, 1.0')
        try:
            values = [float(v.strip()) for v in raw.split(',') if v.strip()]
        except ValueError:
            messages.error(request, 'Invalid temperature values. Use comma-separated numbers.')
            return redirect('runs:parameter_sweep')
        if not values:
            messages.error(request, 'No temperature values provided.')
            return redirect('runs:parameter_sweep')

        with transaction.atomic():
            for temp in values:
                run = BenchmarkRun.objects.create(
                    benchmark=benchmark, provider=provider, model_name=model_name,
                    temperature=temp, max_tokens=max_tokens, num_questions=num_questions,
                    system_prompt=base_system_prompt,
                    tags=f'sweep,sweep_{sweep_uid},temp_{temp}',
                    notes=f'Temperature sweep {sweep_uid} — temp={temp}',
                )
                runs_created.append(run)

    else:  # prompt sweep
        raw = request.POST.get('prompts', '')
        prompts = [p.strip() for p in raw.strip().split('\n---\n') if p.strip()]
        if not prompts:
            messages.error(request, 'No prompts provided. Separate prompts with a line containing only "---".')
            return redirect('runs:parameter_sweep')

        temperature = float(request.POST.get('temperature', 0.0) or 0.0)
        with transaction.atomic():
            for i, prompt in enumerate(prompts, 1):
                run = BenchmarkRun.objects.create(
                    benchmark=benchmark, provider=provider, model_name=model_name,
                    temperature=temperature, max_tokens=max_tokens, num_questions=num_questions,
                    system_prompt=prompt,
                    tags=f'sweep,sweep_{sweep_uid},prompt_{i}',
                    notes=f'Prompt sweep {sweep_uid} — variant {i}',
                )
                runs_created.append(run)

    if worker_mode == 'per_run':
        run_ser = threading.Semaphore(1)
        for run in runs_created:
            start_run_in_background(run.id, run_serializer=run_ser)
    else:
        shared_sem = threading.Semaphore(parallel_workers)
        for run in runs_created:
            start_run_in_background(run.id, shared_semaphore=shared_sem)

    messages.success(
        request,
        f'Created {len(runs_created)} sweep runs (ID: {sweep_uid}). '
        f'Filter by tag "sweep_{sweep_uid}" to track them.'
    )
    from django.urls import reverse
    return redirect(reverse('runs:list') + f'?tag=sweep_{sweep_uid}')


# ---------------------------------------------------------------------------
# Bulk Run
# ---------------------------------------------------------------------------

def bulk_run_view(request):
    """
    Run one benchmark against multiple models in a single submission.

    Each model name (one per line) creates one independent run with shared
    configuration (benchmark, provider, temperature, max_tokens, etc.).
    All runs are tagged 'bulk,bulk_<uid>' for easy filtering.
    """
    benchmarks = Benchmark.objects.filter(loaded_at__isnull=False, is_active=True).order_by('name')
    providers = Provider.objects.filter(is_active=True)

    if request.method == 'GET':
        return render(request, 'runs/bulk_run.html', {
            'benchmarks': benchmarks,
            'providers': providers,
        })

    benchmark_id = request.POST.get('benchmark')
    provider_id = request.POST.get('provider')
    model_names_raw = request.POST.get('model_names', '')
    temperature = float(request.POST.get('temperature', 0.0) or 0.0)
    max_tokens = int(request.POST.get('max_tokens', 512) or 512)
    num_questions = int(request.POST.get('num_questions', 0) or 0)
    system_prompt = request.POST.get('system_prompt', '').strip()
    parallel_workers = int(request.POST.get('parallel_workers', 1) or 1)
    worker_mode = request.POST.get('worker_mode', 'shared')  # 'shared' | 'per_run'
    use_cot = request.POST.get('use_cot', '') == 'on'

    if not benchmark_id or not provider_id:
        messages.error(request, 'Benchmark and provider are required.')
        return redirect('runs:bulk_run')

    model_names = [m.strip() for m in model_names_raw.strip().splitlines() if m.strip()]
    if not model_names:
        messages.error(request, 'Please enter at least one model name.')
        return redirect('runs:bulk_run')

    try:
        benchmark = Benchmark.objects.get(id=benchmark_id)
        provider = Provider.objects.get(id=provider_id)
    except (Benchmark.DoesNotExist, Provider.DoesNotExist):
        messages.error(request, 'Invalid benchmark or provider.')
        return redirect('runs:bulk_run')

    bulk_uid = str(uuid.uuid4())[:8]
    runs_created = []

    with transaction.atomic():
        for model in model_names:
            run = BenchmarkRun.objects.create(
                benchmark=benchmark, provider=provider, model_name=model,
                temperature=temperature, max_tokens=max_tokens, num_questions=num_questions,
                system_prompt=system_prompt, parallel_workers=parallel_workers,
                use_cot=use_cot,
                tags=f'bulk,bulk_{bulk_uid}',
                notes=f'Bulk run {bulk_uid}',
            )
            runs_created.append(run)

    if worker_mode == 'per_run':
        # One run at a time, each using all parallel_workers internally
        run_ser = threading.Semaphore(1)
        for run in runs_created:
            start_run_in_background(run.id, run_serializer=run_ser)
        mode_label = f'{parallel_workers} workers per run, sequentially'
    else:
        # All runs share the worker pool (N total concurrent API calls)
        shared_sem = threading.Semaphore(parallel_workers)
        for run in runs_created:
            start_run_in_background(run.id, shared_semaphore=shared_sem)
        mode_label = f'{parallel_workers} total shared workers'

    messages.success(
        request,
        f'Started {len(runs_created)} runs for {benchmark.name} '
        f'({mode_label}). '
        f'Filter by tag "bulk_{bulk_uid}" to track them together.'
    )
    return redirect('runs:list')
