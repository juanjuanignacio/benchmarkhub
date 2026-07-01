"""
Cancel or delete benchmark runs.

Examples:
    python manage.py bm_cancel 42
    python manage.py bm_cancel 42 43 44
    python manage.py bm_cancel 42 --delete
"""
from django.core.management.base import BaseCommand, CommandError

from apps.runs.models import BenchmarkRun
from apps.runs.runner import cancel_run


class Command(BaseCommand):
    help = 'Cancel or delete benchmark runs'

    def add_arguments(self, parser):
        parser.add_argument('run_ids', nargs='+', type=int, help='Run ID(s)')
        parser.add_argument('--delete', action='store_true',
                            help='Delete the run record after cancelling')

    def handle(self, *args, **options):
        for run_id in options['run_ids']:
            try:
                run = BenchmarkRun.objects.get(id=run_id)
            except BenchmarkRun.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Run #{run_id} not found'))
                continue

            if run.status in ('completed', 'failed', 'cancelled'):
                if options['delete']:
                    run.delete()
                    self.stdout.write(self.style.SUCCESS(f'Run #{run_id} deleted.'))
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Run #{run_id} is already {run.status}. '
                            f'Use --delete to remove it.'
                        )
                    )
                continue

            cancel_run(run_id)
            self.stdout.write(self.style.SUCCESS(f'Run #{run_id} cancelled.'))

            if options['delete']:
                BenchmarkRun.objects.filter(id=run_id).delete()
                self.stdout.write(self.style.SUCCESS(f'Run #{run_id} deleted.'))
