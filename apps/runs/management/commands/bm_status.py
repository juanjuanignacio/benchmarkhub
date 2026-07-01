"""
Check the status of one or more benchmark runs.

Examples:
    python manage.py bm_status 42
    python manage.py bm_status 42 43 44
    python manage.py bm_status 42 --watch
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.runs.models import BenchmarkRun


class Command(BaseCommand):
    help = 'Check the status of benchmark run(s)'

    def add_arguments(self, parser):
        parser.add_argument('run_ids', nargs='+', type=int,
                            help='Run ID(s) to check')
        parser.add_argument('--watch', action='store_true',
                            help='Keep polling until all runs complete (Ctrl+C to stop)')

    def handle(self, *args, **options):
        if options['watch']:
            self._watch(options['run_ids'])
        else:
            for run_id in options['run_ids']:
                self._print_run(run_id)

    def _print_run(self, run_id):
        try:
            run = BenchmarkRun.objects.get(id=run_id)
        except BenchmarkRun.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Run #{run_id} not found'))
            return

        answered = run.results.count()
        status_style = {
            'completed': self.style.SUCCESS,
            'failed': self.style.ERROR,
            'cancelled': self.style.WARNING,
            'running': self.style.HTTP_INFO,
            'pending': self.style.NOTICE,
        }.get(run.status, str)

        self.stdout.write(f'Run #{run.id}')
        self.stdout.write(f'  Benchmark  : {run.benchmark.name}')
        self.stdout.write(f'  Model      : {run.model_name} via {run.provider.name}')
        self.stdout.write(f'  Status     : {status_style(run.status.upper())}')
        if run.status in ('running', 'completed'):
            self.stdout.write(f'  Progress   : {answered}/{run.total_questions}')
            self.stdout.write(f'  Score      : {run.score:.1f}%')
        if run.status == 'failed':
            self.stdout.write(f'  Error      : {run.error_message}')
        if run.duration_seconds:
            self.stdout.write(f'  Duration   : {run.duration_seconds:.0f}s')
        if run.tags:
            self.stdout.write(f'  Tags       : {run.tags}')

    def _watch(self, run_ids):
        self.stdout.write('Watching runs (Ctrl+C to stop)...\n')
        try:
            while True:
                self.stdout.write('\033[H\033[J', ending='')  # clear screen
                done = 0
                for run_id in run_ids:
                    self._print_run(run_id)
                    self.stdout.write('')
                    run = BenchmarkRun.objects.get(id=run_id)
                    if run.status in ('completed', 'failed', 'cancelled'):
                        done += 1
                if done == len(run_ids):
                    self.stdout.write(self.style.SUCCESS('All runs finished.'))
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write('\nStopped watching.')
