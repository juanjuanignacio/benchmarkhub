"""
List runs, benchmarks, providers, or suites.

Examples:
    python manage.py bm_list runs
    python manage.py bm_list runs --status completed --limit 20
    python manage.py bm_list runs --benchmark mmlu --tag baseline
    python manage.py bm_list benchmarks
    python manage.py bm_list benchmarks --loaded
    python manage.py bm_list providers
    python manage.py bm_list suites
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'List runs, benchmarks, providers, or suites'

    def add_arguments(self, parser):
        parser.add_argument(
            'resource',
            choices=['runs', 'benchmarks', 'providers', 'suites'],
            help='What to list',
        )
        # Run filters
        parser.add_argument('--benchmark', help='Filter runs by benchmark slug')
        parser.add_argument('--model', help='Filter runs by model name')
        parser.add_argument('--tag', help='Filter runs by tag')
        parser.add_argument('--status',
                            choices=['pending', 'running', 'completed', 'failed', 'cancelled'],
                            help='Filter runs by status')
        # Benchmark filters
        parser.add_argument('--loaded', action='store_true',
                            help='Show only loaded benchmarks')
        parser.add_argument('--category', help='Filter benchmarks by category')
        # General
        parser.add_argument('--limit', type=int, default=50,
                            help='Maximum rows to show (default: 50)')

    def handle(self, *args, **options):
        resource = options['resource']
        if resource == 'runs':
            self._list_runs(options)
        elif resource == 'benchmarks':
            self._list_benchmarks(options)
        elif resource == 'providers':
            self._list_providers(options)
        elif resource == 'suites':
            self._list_suites(options)

    # ── Runs ─────────────────────────────────────────────────────────────────

    def _list_runs(self, options):
        from apps.runs.models import BenchmarkRun
        qs = BenchmarkRun.objects.select_related('benchmark', 'provider').order_by('-created_at')
        if options.get('benchmark'):
            qs = qs.filter(benchmark__slug=options['benchmark'])
        if options.get('model'):
            qs = qs.filter(model_name__icontains=options['model'])
        if options.get('status'):
            qs = qs.filter(status=options['status'])
        if options.get('tag'):
            qs = qs.filter(tags__icontains=options['tag'])
        qs = qs[:options['limit']]

        if not qs:
            self.stdout.write('No runs found.')
            return

        fmt = '{:<6} {:<22} {:<28} {:<10} {:<8} {}'
        self.stdout.write(self.style.SUCCESS(
            fmt.format('ID', 'BENCHMARK', 'MODEL', 'STATUS', 'SCORE', 'CREATED')
        ))
        self.stdout.write('-' * 90)
        for run in qs:
            score = f'{run.score:.1f}%' if run.score is not None else '-'
            status_fn = {
                'completed': self.style.SUCCESS,
                'failed': self.style.ERROR,
                'cancelled': self.style.WARNING,
                'running': self.style.HTTP_INFO,
            }.get(run.status, str)
            self.stdout.write(fmt.format(
                run.id,
                run.benchmark.slug[:22],
                run.model_name[:28],
                status_fn(run.status[:10]),
                score,
                run.created_at.strftime('%Y-%m-%d %H:%M'),
            ))

    # ── Benchmarks ───────────────────────────────────────────────────────────

    def _list_benchmarks(self, options):
        from apps.benchmarks.models import Benchmark
        qs = Benchmark.objects.order_by('category', 'name')
        if options.get('loaded'):
            qs = qs.filter(loaded_at__isnull=False)
        if options.get('category'):
            qs = qs.filter(category__icontains=options['category'])
        qs = qs[:options['limit']]

        if not qs:
            # Show registry if nothing loaded
            from apps.benchmarks.registry import BENCHMARK_REGISTRY
            self.stdout.write('No benchmarks loaded. Available in registry:')
            for slug in list(BENCHMARK_REGISTRY.keys())[:options['limit']]:
                self.stdout.write(f'  {slug}')
            return

        fmt = '{:<25} {:<15} {:<8} {}'
        self.stdout.write(self.style.SUCCESS(
            fmt.format('SLUG', 'CATEGORY', 'QUESTIONS', 'NAME')
        ))
        self.stdout.write('-' * 75)
        for b in qs:
            loaded = str(b.num_questions) if b.is_loaded else self.style.WARNING('not loaded')
            self.stdout.write(fmt.format(b.slug[:25], b.category[:15], loaded, b.name))

    # ── Providers ────────────────────────────────────────────────────────────

    def _list_providers(self, options):
        from apps.providers.models import Provider
        providers = Provider.objects.order_by('provider_type', 'name')[:options['limit']]
        if not providers:
            self.stdout.write('No providers configured. Add one: python manage.py bm_provider add')
            return

        fmt = '{:<20} {:<12} {:<12} {}'
        self.stdout.write(self.style.SUCCESS(
            fmt.format('SLUG', 'TYPE', 'STATUS', 'NAME')
        ))
        self.stdout.write('-' * 60)
        for p in providers:
            status = self.style.SUCCESS('active') if p.is_active else self.style.WARNING('inactive')
            self.stdout.write(fmt.format(p.slug[:20], p.provider_type[:12], status, p.name))

    # ── Suites ───────────────────────────────────────────────────────────────

    def _list_suites(self, options):
        from apps.benchmarks.models import BenchmarkSuite
        suites = BenchmarkSuite.objects.prefetch_related('items').order_by('name')[:options['limit']]
        if not suites:
            self.stdout.write('No suites found.')
            return

        fmt = '{:<5} {:<30} {}'
        self.stdout.write(self.style.SUCCESS(fmt.format('ID', 'NAME', 'BENCHMARKS')))
        self.stdout.write('-' * 70)
        for s in suites:
            benchmarks = ', '.join(i.benchmark.slug for i in s.items.all())
            self.stdout.write(fmt.format(s.id, s.name[:30], benchmarks or '(empty)'))
