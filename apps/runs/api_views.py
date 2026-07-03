import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from apps.providers.models import Provider
from .models import BenchmarkRun, RunResult


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _benchmark_to_dict(b, include_subjects=False):
    d = {
        'id': b.id,
        'slug': b.slug,
        'name': b.name,
        'description': b.description,
        'category': b.category,
        'benchmark_type': b.benchmark_type,
        'num_questions': b.num_questions,
        'is_loaded': b.is_loaded,
        'loaded_at': b.loaded_at.isoformat() if b.loaded_at else None,
        'metadata': b.metadata or {},
    }
    if include_subjects:
        d['subjects'] = sorted(
            BenchmarkQuestion.objects.filter(benchmark=b)
            .exclude(subject='')
            .values_list('subject', flat=True)
            .distinct()
        )
        # Preview of the default prompt (what a run sends if System Prompt is blank),
        # built from the first question the same way the runner does.
        d['default_prompt'] = None
        try:
            from apps.benchmarks.registry import get_loader
            loader = get_loader(b.slug)
            sample = BenchmarkQuestion.objects.filter(benchmark=b).first()
            if loader and sample:
                if b.prompt_template:
                    d['default_prompt'] = b.prompt_template.format(
                        question=sample.question,
                        choice_a=sample.choice_a or '', choice_b=sample.choice_b or '',
                        choice_c=sample.choice_c or '', choice_d=sample.choice_d or '',
                    )
                else:
                    d['default_prompt'] = loader.format_prompt(sample)
        except Exception:
            d['default_prompt'] = None
    return d


def _run_to_dict(run, include_subject_stats=False):
    d = {
        'id': run.id,
        'benchmark': run.benchmark.slug,
        'benchmark_name': run.benchmark.name,
        'provider': run.provider.slug,
        'provider_name': run.provider.name,
        'model_name': run.model_name,
        'status': run.status,
        'score': round(run.score, 2),
        'total_questions': run.total_questions,
        'correct_answers': run.correct_answers,
        'progress_pct': run.progress_pct,
        'temperature': run.temperature,
        'max_tokens': run.max_tokens,
        'num_questions': run.num_questions,
        'system_prompt': run.system_prompt,
        'use_cot': run.use_cot,
        'few_shot_count': run.few_shot_count,
        'parallel_workers': run.parallel_workers,
        'tags': run.tags,
        'notes': run.notes,
        'error_message': run.error_message or None,
        'created_at': run.created_at.isoformat(),
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'duration_seconds': run.duration_seconds,
        'metadata': run.metadata or {},
    }
    if include_subject_stats:
        subject_qs = (
            run.results.filter(question__subject__isnull=False)
            .exclude(question__subject='')
            .values('question__subject')
            .annotate(total=Count('id'), correct=Count('id', filter=Q(is_correct=True)))
        )
        d['subject_stats'] = {
            s['question__subject']: {
                'total': s['total'],
                'correct': s['correct'],
                'pct': round(s['correct'] / s['total'] * 100, 1) if s['total'] else 0.0,
            }
            for s in subject_qs
        }
    return d


def _result_to_dict(r):
    return {
        'id': r.id,
        'question_id': r.question.question_id,
        'question': r.question.question,
        'subject': r.question.subject,
        'difficulty': r.question.difficulty,
        'correct_answer': r.question.correct_answer,
        'model_response': r.model_response,
        'parsed_answer': r.parsed_answer,
        'is_correct': r.is_correct,
        'response_time': r.response_time,
        'tokens_input': r.tokens_input,
        'tokens_output': r.tokens_output,
        'estimated_cost': r.estimated_cost,
    }


def _paginate(qs, request, default_limit=50, max_limit=500):
    """Return (items, meta_dict) after applying limit/offset from request."""
    try:
        limit = min(int(request.GET.get('limit', default_limit) or default_limit), max_limit)
        offset = max(int(request.GET.get('offset', 0) or 0), 0)
    except (ValueError, TypeError):
        limit, offset = default_limit, 0
    total = qs.count()
    items = qs[offset: offset + limit]
    return items, {'total': total, 'limit': limit, 'offset': offset, 'returned': len(items)}


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
def api_benchmark_list(request):
    """GET /api/v1/benchmarks/  — list all benchmarks."""
    qs = Benchmark.objects.all()
    loaded_only = request.GET.get('loaded', '').lower() in ('1', 'true', 'yes')
    category = request.GET.get('category', '').strip()
    benchmark_type = request.GET.get('type', '').strip()
    if loaded_only:
        qs = qs.filter(loaded_at__isnull=False)
    if category:
        qs = qs.filter(category=category)
    if benchmark_type:
        qs = qs.filter(benchmark_type=benchmark_type)
    qs = qs.order_by('name')
    items, meta = _paginate(qs, request, default_limit=200, max_limit=1000)
    return JsonResponse({
        'benchmarks': [_benchmark_to_dict(b) for b in items],
        **meta,
    })


@require_http_methods(['GET'])
def api_benchmark_detail(request, slug):
    """GET /api/v1/benchmarks/{slug}/  — benchmark detail + subjects."""
    try:
        b = Benchmark.objects.get(slug=slug)
    except Benchmark.DoesNotExist:
        return JsonResponse({'error': 'Benchmark not found'}, status=404)
    return JsonResponse(_benchmark_to_dict(b, include_subjects=True))


@require_http_methods(['GET'])
def api_benchmark_questions(request, slug):
    """GET /api/v1/benchmarks/{slug}/questions/  — paginated question list."""
    try:
        benchmark = Benchmark.objects.get(slug=slug)
    except Benchmark.DoesNotExist:
        return JsonResponse({'error': 'Benchmark not found'}, status=404)

    qs = BenchmarkQuestion.objects.filter(benchmark=benchmark)
    subject = request.GET.get('subject', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    if subject:
        qs = qs.filter(subject=subject)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    qs = qs.order_by('question_id')

    items, meta = _paginate(qs, request, default_limit=100)

    data = []
    for q in items:
        row = {
            'question_id': q.question_id,
            'question': q.question,
            'subject': q.subject,
            'difficulty': q.difficulty,
            'correct_answer': q.correct_answer,
        }
        # Include choices for MCQ
        if q.choice_a:
            row['choices'] = {'A': q.choice_a, 'B': q.choice_b, 'C': q.choice_c, 'D': q.choice_d}
        # Include context for RAG
        if q.context:
            row['context'] = q.context
        data.append(row)

    return JsonResponse({'questions': data, 'benchmark': slug, **meta})


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_run_list_create(request):
    """GET /api/v1/runs/  — list runs with filters.
    POST /api/v1/runs/  — create & start a run."""
    if request.method == 'GET':
        qs = BenchmarkRun.objects.select_related('benchmark', 'provider').all()
        status_filter = request.GET.get('status', '').strip()
        benchmark_filter = request.GET.get('benchmark', '').strip()
        model_filter = request.GET.get('model', '').strip()
        tag_filter = request.GET.get('tag', '').strip()

        if status_filter:
            qs = qs.filter(status=status_filter)
        if benchmark_filter:
            qs = qs.filter(benchmark__slug=benchmark_filter)
        if model_filter:
            qs = qs.filter(model_name__icontains=model_filter)
        if tag_filter:
            qs = qs.filter(tags__icontains=tag_filter)

        qs = qs.order_by('-created_at')
        items, meta = _paginate(qs, request)
        return JsonResponse({'runs': [_run_to_dict(r) for r in items], **meta})

    # POST — create a run
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    benchmark_slug = data.get('benchmark', '').strip()
    provider_slug = data.get('provider', '').strip()
    model_name = data.get('model_name', '').strip()

    if not benchmark_slug or not provider_slug or not model_name:
        return JsonResponse(
            {'error': 'benchmark (slug), provider (slug), and model_name are required'},
            status=400,
        )

    try:
        benchmark = Benchmark.objects.get(slug=benchmark_slug)
    except Benchmark.DoesNotExist:
        return JsonResponse({'error': f'Benchmark "{benchmark_slug}" not found'}, status=404)
    try:
        provider = Provider.objects.get(slug=provider_slug)
    except Provider.DoesNotExist:
        return JsonResponse({'error': f'Provider "{provider_slug}" not found'}, status=404)

    try:
        num_questions = int(data.get('num_questions', 0) or 0)
        temperature = float(data.get('temperature', 0.0) or 0.0)
        max_tokens = int(data.get('max_tokens', 512) or 512)
        parallel_workers = max(1, int(data.get('parallel_workers', 1) or 1))
        few_shot_count = max(0, int(data.get('few_shot_count', 0) or 0))
    except (ValueError, TypeError) as e:
        return JsonResponse({'error': f'Invalid numeric parameter: {e}'}, status=400)

    run = BenchmarkRun.objects.create(
        benchmark=benchmark,
        provider=provider,
        model_name=model_name,
        num_questions=num_questions,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=data.get('system_prompt', ''),
        tags=data.get('tags', ''),
        notes=data.get('notes', ''),
        parallel_workers=parallel_workers,
        few_shot_count=few_shot_count,
        use_cot=bool(data.get('use_cot', False)),
        webhook_url=data.get('webhook_url', ''),
    )

    from .runner import start_run_in_background
    start_run_in_background(run.id)

    return JsonResponse(_run_to_dict(run), status=201)


@require_http_methods(['GET'])
def api_run_detail(request, pk):
    """GET /api/v1/runs/{id}/  — run detail (+ subject_stats if ?subjects=1)."""
    try:
        run = BenchmarkRun.objects.select_related('benchmark', 'provider').get(pk=pk)
    except BenchmarkRun.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)
    include_subjects = request.GET.get('subjects', '') in ('1', 'true')
    return JsonResponse(_run_to_dict(run, include_subject_stats=include_subjects))


@require_http_methods(['GET'])
def api_run_status(request, pk):
    """GET /api/v1/runs/{id}/status/  — lightweight polling endpoint."""
    try:
        run = BenchmarkRun.objects.get(pk=pk)
    except BenchmarkRun.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)
    return JsonResponse({
        'id': run.id,
        'status': run.status,
        'score': round(run.score, 2),
        'total_questions': run.total_questions,
        'correct_answers': run.correct_answers,
        'answered_count': run.results.count(),
        'progress_pct': run.progress_pct,
        'duration_seconds': run.duration_seconds,
        'error_message': run.error_message or None,
    })


@csrf_exempt
@require_http_methods(['POST'])
def api_run_cancel(request, pk):
    """POST /api/v1/runs/{id}/cancel/  — cancel a running run."""
    try:
        run = BenchmarkRun.objects.get(pk=pk)
    except BenchmarkRun.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)

    if run.status not in ('running', 'pending'):
        return JsonResponse({'error': f'Run is not cancellable (status: {run.status})'}, status=400)

    from .runner import cancel_run
    cancel_run(pk)
    return JsonResponse({'cancelled': True, 'id': pk})


@csrf_exempt
@require_http_methods(['DELETE'])
def api_run_delete(request, pk):
    """DELETE /api/v1/runs/{id}/  — delete a run and all its results."""
    try:
        run = BenchmarkRun.objects.get(pk=pk)
        run.delete()
        return JsonResponse({'deleted': True, 'id': pk})
    except BenchmarkRun.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)


@require_http_methods(['GET'])
def api_run_results(request, pk):
    """GET /api/v1/runs/{id}/results/  — paginated per-question results.
    Query params: correct (true/false), subject, limit, offset."""
    try:
        run = BenchmarkRun.objects.get(pk=pk)
    except BenchmarkRun.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)

    qs = RunResult.objects.filter(run=run).select_related('question').order_by('id')

    correct_param = request.GET.get('correct', '').lower()
    if correct_param == 'true':
        qs = qs.filter(is_correct=True)
    elif correct_param == 'false':
        qs = qs.filter(is_correct=False)

    subject_param = request.GET.get('subject', '').strip()
    if subject_param:
        qs = qs.filter(question__subject=subject_param)

    items, meta = _paginate(qs, request, default_limit=100)
    return JsonResponse({'results': [_result_to_dict(r) for r in items], 'run_id': pk, **meta})


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
def api_provider_list(request):
    """GET /api/v1/providers/  — list all providers."""
    qs = Provider.objects.all().order_by('name')
    active_only = request.GET.get('active', '').lower() in ('1', 'true', 'yes')
    if active_only:
        qs = qs.filter(is_active=True)
    data = [
        {
            'id': p.id,
            'slug': p.slug,
            'name': p.name,
            'provider_type': p.provider_type,
            'is_active': p.is_active,
            'default_model': p.default_model,
            'base_url': p.base_url or None,
        }
        for p in qs
    ]
    return JsonResponse({'providers': data, 'count': len(data)})


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
def api_leaderboard(request):
    """GET /api/v1/leaderboard/  — best score per model per benchmark.
    Query params: benchmark (slug), limit."""
    qs = BenchmarkRun.objects.filter(status='completed').select_related('benchmark', 'provider')
    benchmark_filter = request.GET.get('benchmark', '').strip()
    if benchmark_filter:
        qs = qs.filter(benchmark__slug=benchmark_filter)
    qs = qs.order_by('benchmark__name', '-score', '-created_at')

    # One entry per (benchmark, model_name) keeping the best score
    seen = {}
    entries = []
    for run in qs:
        key = (run.benchmark_id, run.model_name)
        if key not in seen:
            seen[key] = True
            entries.append({
                'benchmark': run.benchmark.slug,
                'benchmark_name': run.benchmark.name,
                'model_name': run.model_name,
                'provider': run.provider.slug,
                'score': round(run.score, 2),
                'correct_answers': run.correct_answers,
                'total_questions': run.total_questions,
                'run_id': run.id,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            })

    try:
        limit = min(int(request.GET.get('limit', 100) or 100), 1000)
    except (ValueError, TypeError):
        limit = 100

    return JsonResponse({'leaderboard': entries[:limit], 'count': len(entries[:limit])})
