"""
Manage and run benchmark suites.

Examples:
    python manage.py bm_suite list
    python manage.py bm_suite create "Clinical Suite" mmlu medqa arc_challenge
    python manage.py bm_suite run 1 ollama llama3.2
    python manage.py bm_suite run 1 ollama llama3.2 --parallel --wait
    python manage.py bm_suite delete 1
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.benchmarks.models import Benchmark, BenchmarkSuite, BenchmarkSuiteItem
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun, BenchmarkSuiteRun
from apps.runs.runner import start_run_in_background


class Command(BaseCommand):
    help = 'Manage and run benchmark suites'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', required=True)

        # list
        subparsers.add_parser('list', help='List all suites')

        # create
        p_create = subparsers.add_parser('create', help='Create a new suite')
        p_create.add_argument('name', help='Suite name')
        p_create.add_argument('benchmarks', nargs='+', help='Benchmark slugs to include')
        p_create.add_argument('--description', default='')

        # run
        p_run = subparsers.add_parser('run', help='Run a suite against a model')
        p_run.add_argument('suite_id', type=int, help='Suite ID')
        p_run.add_argument('provider', help='Provider slug')
        p_run.add_argument('model', help='Model name')
        p_run.add_argument('--temperature', type=float, default=0.0)
        p_run.add_argument('--max-tokens', type=int, default=512)
        p_run.add_argument('--num-questions', type=int, default=0,
                           help='Questions per benchmark (0 = all)')
        p_run.add_argument('--system-prompt', default='')
        p_run.add_argument('--parallel', action='store_true',
                           help='Run all benchmarks in parallel (default: sequential)')
        p_run.add_argument('--wait', action='store_true')

        # delete
        p_del = subparsers.add_parser('delete', help='Delete a suite')
        p_del.add_argument('suite_id', type=int)

    def handle(self, *args, **options):
        action = options['action']
        if action == 'list':
            self._list()
        elif action == 'create':
            self._create(options)
        elif action == 'run':
            self._run(options)
        elif action == 'delete':
            self._delete(options)

    # ── List ─────────────────────────────────────────────────────────────────

    def _list(self):
        suites = BenchmarkSuite.objects.prefetch_related('items__benchmark').order_by('name')
        if not suites:
            self.stdout.write('No suites. Create one: python manage.py bm_suite create "Name" slug1 slug2')
            return
        for s in suites:
            benchmarks = ', '.join(i.benchmark.slug for i in s.items.order_by('order'))
            self.stdout.write(f'  [{s.id}] {s.name}')
            self.stdout.write(f'        Benchmarks: {benchmarks or "(empty)"}')

    # ── Create ───────────────────────────────────────────────────────────────

    def _create(self, options):
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', options['name'].lower()).strip('-')
        suite = BenchmarkSuite.objects.create(
            name=options['name'],
            slug=slug,
            description=options.get('description', ''),
        )
        for order, b_slug in enumerate(options['benchmarks']):
            try:
                benchmark = Benchmark.objects.get(slug=b_slug)
            except Benchmark.DoesNotExist:
                suite.delete()
                raise CommandError(
                    f"Benchmark '{b_slug}' not found. "
                    f"Use: python manage.py bm_list benchmarks"
                )
            BenchmarkSuiteItem.objects.create(suite=suite, benchmark=benchmark, order=order)

        self.stdout.write(self.style.SUCCESS(
            f'Suite #{suite.id} "{suite.name}" created with '
            f'{len(options["benchmarks"])} benchmark(s).'
        ))

    # ── Run ──────────────────────────────────────────────────────────────────

    def _run(self, options):
        try:
            suite = BenchmarkSuite.objects.prefetch_related('items__benchmark').get(
                id=options['suite_id']
            )
        except BenchmarkSuite.DoesNotExist:
            raise CommandError(f"Suite #{options['suite_id']} not found.")

        try:
            provider = Provider.objects.get(slug=options['provider'])
        except Provider.DoesNotExist:
            raise CommandError(f"Provider '{options['provider']}' not found.")

        items = list(suite.items.select_related('benchmark').order_by('order'))
        if not items:
            raise CommandError(f'Suite "{suite.name}" has no benchmarks.')

        suite_run = BenchmarkSuiteRun.objects.create(
            suite=suite,
            provider=provider,
            model_name=options['model'],
            status='running',
            num_questions_per_benchmark=options['num_questions'],
            temperature=options['temperature'],
            max_tokens=options['max_tokens'],
            system_prompt=options['system_prompt'],
        )

        run_ids = []
        for item in items:
            if not item.benchmark.is_loaded:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Skipping {item.benchmark.slug} (not loaded)'
                    )
                )
                continue
            run = BenchmarkRun.objects.create(
                benchmark=item.benchmark,
                provider=provider,
                model_name=options['model'],
                temperature=options['temperature'],
                max_tokens=options['max_tokens'],
                num_questions=options['num_questions'],
                system_prompt=options['system_prompt'],
                suite_run=suite_run,
                status='pending',
            )
            run_ids.append(run.id)
            self.stdout.write(f'  Created Run #{run.id}: {item.benchmark.slug}')

        if options.get('parallel'):
            for run_id in run_ids:
                start_run_in_background(run_id)
            self.stdout.write(f'  All {len(run_ids)} runs started in parallel.')
        else:
            # Sequential: start runs one by one (fire background but wait between)
            for run_id in run_ids:
                start_run_in_background(run_id)
            self.stdout.write(f'  {len(run_ids)} runs queued sequentially.')

        self.stdout.write(self.style.SUCCESS(
            f'\nSuite run #{suite_run.id} for "{suite.name}" — {len(run_ids)} benchmarks'
        ))

        if options.get('wait'):
            self._wait_all(run_ids, suite_run)

    def _wait_all(self, run_ids, suite_run):
        self.stdout.write('\nWaiting for suite to complete...')
        while True:
            runs = list(BenchmarkRun.objects.filter(id__in=run_ids))
            done = [r for r in runs if r.status in ('completed', 'failed', 'cancelled')]
            self.stdout.write(f'\r  {len(done)}/{len(run_ids)} benchmarks done  ', ending='')
            self.stdout.flush()
            if len(done) == len(run_ids):
                break
            time.sleep(2)
        self.stdout.write('')
        suite_run.refresh_from_db()
        total_score = suite_run.total_score
        self.stdout.write(self.style.SUCCESS(
            f'\nSuite run #{suite_run.id} complete — Avg score: {total_score:.1f}%'
        ))
        for run in BenchmarkRun.objects.filter(id__in=run_ids).order_by('id'):
            score = f'{run.score:.1f}%' if run.score is not None else 'N/A'
            fn = self.style.SUCCESS if run.status == 'completed' else self.style.ERROR
            self.stdout.write(fn(f'  {run.benchmark.slug:<25} {score}'))

    # ── Delete ───────────────────────────────────────────────────────────────

    def _delete(self, options):
        try:
            suite = BenchmarkSuite.objects.get(id=options['suite_id'])
        except BenchmarkSuite.DoesNotExist:
            raise CommandError(f"Suite #{options['suite_id']} not found.")
        name = suite.name
        suite.delete()
        self.stdout.write(self.style.SUCCESS(f'Suite "{name}" deleted.'))
