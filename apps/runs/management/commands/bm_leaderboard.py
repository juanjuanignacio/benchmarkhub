"""
Show the leaderboard: best score per model per benchmark.

Examples:
    python manage.py bm_leaderboard
    python manage.py bm_leaderboard --benchmark mmlu
    python manage.py bm_leaderboard --limit 20
"""
from django.core.management.base import BaseCommand
from django.db.models import Max


class Command(BaseCommand):
    help = 'Display leaderboard of best scores per model per benchmark'

    def add_arguments(self, parser):
        parser.add_argument('--benchmark', help='Filter by benchmark slug')
        parser.add_argument('--limit', type=int, default=30,
                            help='Maximum rows to show (default: 30)')

    def handle(self, *args, **options):
        from apps.runs.models import BenchmarkRun

        qs = (
            BenchmarkRun.objects
            .filter(status='completed')
            .select_related('benchmark')
        )
        if options.get('benchmark'):
            qs = qs.filter(benchmark__slug=options['benchmark'])

        # Best run per (benchmark, model)
        from django.db.models import Max
        best = {}
        for run in qs.order_by('-score'):
            key = (run.benchmark.slug, run.model_name)
            if key not in best:
                best[key] = run

        entries = sorted(best.values(), key=lambda r: (-r.score, r.benchmark.slug))
        entries = entries[:options['limit']]

        if not entries:
            self.stdout.write('No completed runs found.')
            return

        fmt = '{:<5} {:<22} {:<28} {:<8} {}'
        self.stdout.write(self.style.SUCCESS(
            fmt.format('RANK', 'BENCHMARK', 'MODEL', 'SCORE', 'RUN ID')
        ))
        self.stdout.write('-' * 75)
        for rank, run in enumerate(entries, 1):
            score_str = f'{run.score:.1f}%'
            color_fn = (
                self.style.SUCCESS if run.score >= 70 else
                self.style.WARNING if run.score >= 50 else
                self.style.ERROR
            )
            self.stdout.write(fmt.format(
                rank,
                run.benchmark.slug[:22],
                run.model_name[:28],
                color_fn(score_str),
                run.id,
            ))
