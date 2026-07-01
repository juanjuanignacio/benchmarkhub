"""
Parameter sweep: run a benchmark across a range of temperatures or prompts.

Examples:
    # Temperature sweep from 0.0 to 1.0 in steps of 0.25
    python manage.py bm_sweep mmlu ollama llama3.2 --temp-range 0.0 1.0 0.25

    # Prompt sweep using saved prompt IDs (or --prompt-texts for inline)
    python manage.py bm_sweep mmlu ollama llama3.2 --prompt-ids 1 2 3

    # List saved prompts
    python manage.py bm_sweep --list-prompts
"""
import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.benchmarks.models import Benchmark, PromptTemplate
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun
from apps.runs.runner import start_run_in_background


class Command(BaseCommand):
    help = 'Parameter sweep: run a benchmark with varying temperatures or prompts'

    def add_arguments(self, parser):
        parser.add_argument('benchmark', nargs='?', help='Benchmark slug')
        parser.add_argument('provider', nargs='?', help='Provider slug')
        parser.add_argument('model', nargs='?', help='Model name')

        parser.add_argument('--temp-range', nargs=3, type=float,
                            metavar=('MIN', 'MAX', 'STEP'),
                            help='Temperature sweep: min max step (e.g. 0.0 1.0 0.25)')
        parser.add_argument('--prompt-ids', nargs='+', type=int,
                            metavar='ID',
                            help='Prompt sweep: list of PromptTemplate IDs')
        parser.add_argument('--prompt-texts', nargs='+',
                            metavar='TEXT',
                            help='Prompt sweep: inline prompt strings')

        parser.add_argument('--temperature', type=float, default=0.0,
                            help='Fixed temperature for prompt sweeps (default: 0.0)')
        parser.add_argument('--max-tokens', type=int, default=512)
        parser.add_argument('--num-questions', type=int, default=0)
        parser.add_argument('--few-shot', type=int, default=0)
        parser.add_argument('--cot', action='store_true')
        parser.add_argument('--workers', type=int, default=1)
        parser.add_argument('--tags', type=str, default='')
        parser.add_argument('--wait', action='store_true')
        parser.add_argument('--list-prompts', action='store_true',
                            help='List saved prompts and exit')

    def handle(self, *args, **options):
        if options['list_prompts']:
            self._list_prompts()
            return

        for field in ('benchmark', 'provider', 'model'):
            if not options.get(field):
                raise CommandError(f'--{field} is required. '
                                   f'Use --list-prompts to see saved prompts.')

        if not options['temp_range'] and not options['prompt_ids'] and not options['prompt_texts']:
            raise CommandError(
                'Specify one of: --temp-range MIN MAX STEP, '
                '--prompt-ids ID..., or --prompt-texts TEXT...'
            )

        try:
            benchmark = Benchmark.objects.get(slug=options['benchmark'])
        except Benchmark.DoesNotExist:
            raise CommandError(f"Benchmark '{options['benchmark']}' not found.")
        if not benchmark.is_loaded:
            raise CommandError(
                f"Benchmark '{benchmark.slug}' is not loaded. "
                f"Run: python manage.py load_benchmark {benchmark.slug}"
            )

        try:
            provider = Provider.objects.get(slug=options['provider'])
        except Provider.DoesNotExist:
            raise CommandError(f"Provider '{options['provider']}' not found.")

        sweep_id = str(uuid.uuid4())[:8]
        sweep_tag = f'sweep_{sweep_id}'
        base_tags = options['tags']
        tags = f'{sweep_tag},{base_tags}'.strip(',') if base_tags else sweep_tag

        run_ids = []

        if options['temp_range']:
            min_t, max_t, step = options['temp_range']
            temps = []
            t = min_t
            while t <= max_t + 1e-9:
                temps.append(round(t, 4))
                t += step
            self.stdout.write(f'Temperature sweep: {temps}')
            for temp in temps:
                run = self._create_run(
                    benchmark, provider, options['model'],
                    temperature=temp,
                    system_prompt='',
                    options=options,
                    tags=tags,
                )
                run_ids.append(run.id)
                self.stdout.write(f'  Started Run #{run.id} — temp={temp}')

        else:
            prompts = []
            if options['prompt_ids']:
                for pid in options['prompt_ids']:
                    try:
                        pt = PromptTemplate.objects.get(id=pid)
                        prompts.append((pt.name, pt.content))
                    except PromptTemplate.DoesNotExist:
                        raise CommandError(f"PromptTemplate ID {pid} not found. "
                                           f"Use --list-prompts to see available.")
            else:
                for i, text in enumerate(options['prompt_texts'], 1):
                    prompts.append((f'prompt_{i}', text))

            self.stdout.write(f'Prompt sweep: {len(prompts)} variants')
            for name, content in prompts:
                run = self._create_run(
                    benchmark, provider, options['model'],
                    temperature=options['temperature'],
                    system_prompt=content,
                    options=options,
                    tags=tags,
                )
                run.notes = f'Prompt: {name}'
                run.save(update_fields=['notes'])
                run_ids.append(run.id)
                self.stdout.write(f'  Started Run #{run.id} — prompt: {name}')

        self.stdout.write(self.style.SUCCESS(
            f'\n{len(run_ids)} run(s) started — sweep ID: {sweep_tag}'
        ))

        if options['wait']:
            self._wait_all(run_ids)
        else:
            ids_str = ' '.join(str(i) for i in run_ids)
            self.stdout.write(f'Check status: python manage.py bm_status {ids_str}')

    def _create_run(self, benchmark, provider, model_name,
                    temperature, system_prompt, options, tags):
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            max_tokens=options['max_tokens'],
            num_questions=options['num_questions'],
            system_prompt=system_prompt,
            few_shot_count=options['few_shot'],
            use_cot=options['cot'],
            parallel_workers=max(1, options['workers']),
            tags=tags,
            status='pending',
        )
        start_run_in_background(run.id)
        return run

    def _list_prompts(self):
        from apps.benchmarks.models import PromptTemplate
        prompts = PromptTemplate.objects.order_by('name')
        if not prompts:
            self.stdout.write('No saved prompts. Create one in the web UI → Benchmarks → Prompt Library.')
            return
        fmt = '{:<5} {:<30} {}'
        self.stdout.write(self.style.SUCCESS(fmt.format('ID', 'NAME', 'PREVIEW')))
        self.stdout.write('-' * 70)
        for p in prompts:
            preview = p.content[:60].replace('\n', ' ')
            self.stdout.write(fmt.format(p.id, p.name[:30], preview))

    def _wait_all(self, run_ids):
        self.stdout.write('\nWaiting...')
        while True:
            runs = BenchmarkRun.objects.filter(id__in=run_ids)
            done = [r for r in runs if r.status in ('completed', 'failed', 'cancelled')]
            self.stdout.write(f'\r  {len(done)}/{len(run_ids)} done  ', ending='')
            self.stdout.flush()
            if len(done) == len(run_ids):
                break
            time.sleep(2)
        self.stdout.write('')
        for run in BenchmarkRun.objects.filter(id__in=run_ids).order_by('id'):
            score = f'{run.score:.1f}%' if run.score is not None else 'N/A'
            note = f' ({run.notes})' if run.notes else ''
            fn = self.style.SUCCESS if run.status == 'completed' else self.style.ERROR
            self.stdout.write(fn(f'  Run #{run.id} {score}{note}'))
