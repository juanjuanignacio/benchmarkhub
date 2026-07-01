"""
Create and start a benchmark run from the command line.

Examples:
    python manage.py bm_run mmlu ollama llama3.2
    python manage.py bm_run medqa openai gpt-4o --temperature 0 --wait
    python manage.py bm_run arc_challenge anthropic claude-3-5-sonnet-20241022 \\
        --num-questions 100 --system-prompt "Answer with a single letter." \\
        --few-shot 3 --cot --tags baseline,v1 --wait
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.benchmarks.models import Benchmark
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun
from apps.runs.runner import start_run_in_background


class Command(BaseCommand):
    help = 'Create and start a benchmark run'

    def add_arguments(self, parser):
        parser.add_argument('benchmark', help='Benchmark slug (e.g. mmlu, medqa)')
        parser.add_argument('provider', help='Provider slug (e.g. ollama, openai)')
        parser.add_argument('model', help='Model name (e.g. llama3.2, gpt-4o)')
        parser.add_argument('--temperature', type=float, default=0.0,
                            help='Sampling temperature (default: 0.0)')
        parser.add_argument('--max-tokens', type=int, default=512,
                            help='Maximum output tokens (default: 512)')
        parser.add_argument('--num-questions', type=int, default=0,
                            help='Number of questions to evaluate (0 = all, default: 0)')
        parser.add_argument('--system-prompt', type=str, default='',
                            help='System prompt text')
        parser.add_argument('--few-shot', type=int, default=0,
                            help='Number of few-shot examples (default: 0)')
        parser.add_argument('--cot', action='store_true',
                            help='Enable chain-of-thought (appends "Let\'s think step by step")')
        parser.add_argument('--workers', type=int, default=1,
                            help='Parallel workers (default: 1)')
        parser.add_argument('--tags', type=str, default='',
                            help='Comma-separated tags (e.g. baseline,v1)')
        parser.add_argument('--notes', type=str, default='',
                            help='Free-text notes for this run')
        parser.add_argument('--webhook', type=str, default='',
                            help='Webhook URL to notify on completion')
        parser.add_argument('--wait', action='store_true',
                            help='Wait for the run to complete and print final score')

    def handle(self, *args, **options):
        # Resolve benchmark
        try:
            benchmark = Benchmark.objects.get(slug=options['benchmark'])
        except Benchmark.DoesNotExist:
            raise CommandError(
                f"Benchmark '{options['benchmark']}' not found. "
                f"Run: python manage.py load_benchmark --list"
            )
        if not benchmark.is_loaded:
            raise CommandError(
                f"Benchmark '{benchmark.slug}' is not loaded. "
                f"Run: python manage.py load_benchmark {benchmark.slug}"
            )

        # Resolve provider
        try:
            provider = Provider.objects.get(slug=options['provider'])
        except Provider.DoesNotExist:
            raise CommandError(
                f"Provider '{options['provider']}' not found. "
                f"Run: python manage.py bm_provider list"
            )

        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            provider=provider,
            model_name=options['model'],
            temperature=options['temperature'],
            max_tokens=options['max_tokens'],
            num_questions=options['num_questions'],
            system_prompt=options['system_prompt'],
            few_shot_count=options['few_shot'],
            use_cot=options['cot'],
            parallel_workers=max(1, options['workers']),
            tags=options['tags'],
            notes=options['notes'],
            webhook_url=options['webhook'],
            status='pending',
        )

        start_run_in_background(run.id)

        self.stdout.write(
            self.style.SUCCESS(f'Run #{run.id} started — '
                               f'{benchmark.name} / {options["model"]}')
        )
        self.stdout.write(f'  Temperature : {options["temperature"]}')
        self.stdout.write(f'  Max tokens  : {options["max_tokens"]}')
        if options['num_questions']:
            self.stdout.write(f'  Questions   : {options["num_questions"]}')
        if options['few_shot']:
            self.stdout.write(f'  Few-shot    : {options["few_shot"]}')
        if options['cot']:
            self.stdout.write(f'  CoT         : enabled')

        if options['wait']:
            self._wait_for_run(run.id)
        else:
            self.stdout.write(
                f'\nCheck status: python manage.py bm_status {run.id}'
            )

    def _wait_for_run(self, run_id):
        self.stdout.write('\nWaiting for run to complete...')
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        idx = 0
        while True:
            run = BenchmarkRun.objects.get(id=run_id)
            if run.status in ('completed', 'failed', 'cancelled'):
                break
            answered = run.results.count()
            total = run.total_questions or '?'
            self.stdout.write(
                f'\r  {spinner[idx % len(spinner)]} {answered}/{total} questions answered  ',
                ending=''
            )
            self.stdout.flush()
            idx += 1
            time.sleep(1)

        self.stdout.write('')
        run = BenchmarkRun.objects.get(id=run_id)
        if run.status == 'completed':
            color = self.style.SUCCESS if run.score >= 70 else (
                self.style.WARNING if run.score >= 50 else self.style.ERROR
            )
            self.stdout.write(color(
                f'\nRun #{run_id} completed — Score: {run.score:.1f}% '
                f'({run.correct_answers}/{run.total_questions} correct)'
            ))
        elif run.status == 'failed':
            self.stdout.write(self.style.ERROR(
                f'\nRun #{run_id} FAILED: {run.error_message}'
            ))
        else:
            self.stdout.write(self.style.WARNING(f'\nRun #{run_id} {run.status}'))
