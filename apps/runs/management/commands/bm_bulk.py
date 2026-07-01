"""
Bulk run: evaluate one or more benchmarks against multiple models at once.

Examples:
    python manage.py bm_bulk mmlu ollama/llama3.2 openai/gpt-4o
    python manage.py bm_bulk mmlu medqa ollama/llama3.2 openai/gpt-4o --temperature 0 --wait
    python manage.py bm_bulk arc_challenge ollama/mistral --num-questions 200 --tag bulk-test
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.benchmarks.models import Benchmark
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun
from apps.runs.runner import start_run_in_background


def _resolve_provider_model(spec):
    """Parse 'provider_slug/model_name' or raise CommandError."""
    if '/' not in spec:
        raise CommandError(
            f"Model spec '{spec}' must be in format provider_slug/model_name "
            f"(e.g. ollama/llama3.2). Use: python manage.py bm_provider list"
        )
    provider_slug, model_name = spec.split('/', 1)
    try:
        provider = Provider.objects.get(slug=provider_slug)
    except Provider.DoesNotExist:
        raise CommandError(
            f"Provider '{provider_slug}' not found. "
            f"Run: python manage.py bm_provider list"
        )
    return provider, model_name


class Command(BaseCommand):
    help = 'Run one or more benchmarks against multiple models in a single operation'

    def add_arguments(self, parser):
        parser.add_argument(
            'specs',
            nargs='+',
            metavar='BENCHMARK_OR_MODEL',
            help=(
                'Mix of benchmark slugs and model specs (provider/model). '
                'Benchmarks and models are separated automatically: anything '
                'containing "/" is treated as a model spec.'
            ),
        )
        parser.add_argument('--temperature', type=float, default=0.0)
        parser.add_argument('--max-tokens', type=int, default=512)
        parser.add_argument('--num-questions', type=int, default=0)
        parser.add_argument('--system-prompt', type=str, default='')
        parser.add_argument('--few-shot', type=int, default=0)
        parser.add_argument('--cot', action='store_true')
        parser.add_argument('--workers', type=int, default=1)
        parser.add_argument('--tags', type=str, default='',
                            help='Extra tags (the bulk ID is added automatically)')
        parser.add_argument('--wait', action='store_true',
                            help='Wait for all runs to complete')

    def handle(self, *args, **options):
        benchmark_slugs = [s for s in options['specs'] if '/' not in s]
        model_specs    = [s for s in options['specs'] if '/' in s]

        if not benchmark_slugs:
            raise CommandError('Provide at least one benchmark slug (without "/").')
        if not model_specs:
            raise CommandError(
                'Provide at least one model spec as provider_slug/model_name '
                '(e.g. ollama/llama3.2).'
            )

        # Validate benchmarks
        benchmarks = []
        for slug in benchmark_slugs:
            try:
                b = Benchmark.objects.get(slug=slug)
            except Benchmark.DoesNotExist:
                raise CommandError(f"Benchmark '{slug}' not found.")
            if not b.is_loaded:
                raise CommandError(
                    f"Benchmark '{slug}' is not loaded. "
                    f"Run: python manage.py load_benchmark {slug}"
                )
            benchmarks.append(b)

        # Validate providers/models
        provider_models = [_resolve_provider_model(s) for s in model_specs]

        import uuid
        bulk_id = str(uuid.uuid4())[:8]
        base_tags = options['tags']
        bulk_tag = f'bulk_{bulk_id}'
        tags = f'{bulk_tag},{base_tags}'.strip(',') if base_tags else bulk_tag

        run_ids = []
        for benchmark in benchmarks:
            for provider, model_name in provider_models:
                run = BenchmarkRun.objects.create(
                    benchmark=benchmark,
                    provider=provider,
                    model_name=model_name,
                    temperature=options['temperature'],
                    max_tokens=options['max_tokens'],
                    num_questions=options['num_questions'],
                    system_prompt=options['system_prompt'],
                    few_shot_count=options['few_shot'],
                    use_cot=options['cot'],
                    parallel_workers=max(1, options['workers']),
                    tags=tags,
                    status='pending',
                )
                start_run_in_background(run.id)
                run_ids.append(run.id)
                self.stdout.write(
                    f'  Started Run #{run.id}: {benchmark.slug} / {model_name}'
                )

        total = len(run_ids)
        self.stdout.write(self.style.SUCCESS(
            f'\n{total} run(s) started — bulk ID: {bulk_tag}'
        ))
        self.stdout.write(
            f'Filter in UI: Runs list → Tag = {bulk_tag}'
        )

        if options['wait']:
            self._wait_all(run_ids)
        else:
            ids_str = ' '.join(str(i) for i in run_ids)
            self.stdout.write(f'\nCheck status: python manage.py bm_status {ids_str}')

    def _wait_all(self, run_ids):
        self.stdout.write('\nWaiting for all runs...')
        while True:
            runs = BenchmarkRun.objects.filter(id__in=run_ids)
            done = [r for r in runs if r.status in ('completed', 'failed', 'cancelled')]
            self.stdout.write(
                f'\r  {len(done)}/{len(run_ids)} finished  ', ending=''
            )
            self.stdout.flush()
            if len(done) == len(run_ids):
                break
            time.sleep(2)
        self.stdout.write('')
        runs = BenchmarkRun.objects.filter(id__in=run_ids)
        for run in runs.order_by('id'):
            score = f'{run.score:.1f}%' if run.score is not None else 'N/A'
            fn = self.style.SUCCESS if run.status == 'completed' else self.style.ERROR
            self.stdout.write(fn(
                f'  Run #{run.id} {run.status:<10} '
                f'{run.benchmark.slug:<20} {run.model_name:<25} {score}'
            ))
