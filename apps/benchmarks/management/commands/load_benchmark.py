"""
Management command to load benchmark questions into the database.

Usage:
    python manage.py load_benchmark mmlu --samples 100
    python manage.py load_benchmark arc_challenge
    python manage.py load_benchmark --list
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from apps.benchmarks.registry import BENCHMARK_REGISTRY, get_loader

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load benchmark questions from HuggingFace datasets into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            'slug',
            nargs='?',
            type=str,
            help='The slug of the benchmark to load (e.g. mmlu, arc_challenge)',
        )
        parser.add_argument(
            '--samples',
            type=int,
            default=0,
            help='Number of samples to load (0 = all)',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            dest='list_benchmarks',
            help='List all available benchmarks',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            dest='load_all',
            help='Load all benchmarks',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload even if already loaded',
        )

    def handle(self, *args, **options):
        if options['list_benchmarks']:
            self.list_benchmarks()
            return

        if options['load_all']:
            for slug in BENCHMARK_REGISTRY:
                self.load_benchmark(slug, options['samples'], options['force'])
            return

        slug = options.get('slug')
        if not slug:
            raise CommandError(
                'Please specify a benchmark slug or use --list to see available benchmarks'
            )

        self.load_benchmark(slug, options['samples'], options['force'])

    def list_benchmarks(self):
        self.stdout.write(self.style.SUCCESS('Available benchmarks:'))
        self.stdout.write('-' * 80)
        for slug, loader_cls in BENCHMARK_REGISTRY.items():
            loader = loader_cls()
            btype = getattr(loader, 'benchmark_type', 'text')
            type_tag = {'text': '', 'vision': '[IMG]', 'audio': '[AUD]', 'agentic': '[AGT]'}.get(btype, '')
            try:
                bench = Benchmark.objects.get(slug=slug)
                status = self.style.SUCCESS(f'LOADED ({bench.num_questions} questions)')
            except Benchmark.DoesNotExist:
                status = self.style.WARNING('not loaded')
            self.stdout.write(f'  {slug:<22} [{loader.category:<12}] {type_tag:>5} {loader.name} - {status}')

    def load_benchmark(self, slug, num_samples=0, force=False):
        loader = get_loader(slug)
        if not loader:
            raise CommandError(f'Unknown benchmark slug: {slug}. Use --list to see available.')

        # Check if already loaded
        try:
            benchmark = Benchmark.objects.get(slug=slug)
            if benchmark.is_loaded and not force:
                self.stdout.write(
                    self.style.WARNING(
                        f'Benchmark {slug} already loaded with {benchmark.num_questions} questions. '
                        f'Use --force to reload.'
                    )
                )
                return
        except Benchmark.DoesNotExist:
            benchmark = None

        self.stdout.write(f'Loading {loader.name}...')
        try:
            questions_data = loader.load_questions()
        except Exception as e:
            raise CommandError(f'Error loading questions from dataset: {e}')

        if num_samples and num_samples > 0:
            questions_data = questions_data[:num_samples]
            self.stdout.write(f'  Using first {num_samples} samples')

        self.stdout.write(f'  Got {len(questions_data)} questions')

        benchmark_type = getattr(loader, 'benchmark_type', 'text')

        with transaction.atomic():
            if benchmark is None:
                benchmark = Benchmark.objects.create(
                    slug=slug,
                    name=loader.name,
                    description=loader.description,
                    category=loader.category,
                    benchmark_type=benchmark_type,
                )
            else:
                benchmark.name = loader.name
                benchmark.description = loader.description
                benchmark.category = loader.category
                benchmark.benchmark_type = benchmark_type
                benchmark.save()

            BenchmarkQuestion.objects.filter(benchmark=benchmark).delete()

            batch = []
            for qdata in questions_data:
                batch.append(BenchmarkQuestion(
                    benchmark=benchmark,
                    question_id=str(qdata['question_id']),
                    question=qdata['question'],
                    choice_a=qdata.get('choice_a'),
                    choice_b=qdata.get('choice_b'),
                    choice_c=qdata.get('choice_c'),
                    choice_d=qdata.get('choice_d'),
                    correct_answer=str(qdata.get('correct_answer', '')),
                    subject=str(qdata.get('subject', '')),
                    difficulty=str(qdata.get('difficulty', '')),
                    context=str(qdata.get('context', '')),
                    image_paths=qdata.get('image_paths', []),
                    audio_path=str(qdata.get('audio_path', '')),
                    metadata=qdata.get('metadata', {}),
                ))
                if len(batch) >= 500:
                    BenchmarkQuestion.objects.bulk_create(batch, ignore_conflicts=True)
                    batch = []
                    self.stdout.write('.', ending='')
                    self.stdout.flush()
            if batch:
                BenchmarkQuestion.objects.bulk_create(batch, ignore_conflicts=True)

            benchmark.num_questions = BenchmarkQuestion.objects.filter(benchmark=benchmark).count()
            benchmark.loaded_at = timezone.now()
            benchmark.save()

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully loaded {benchmark.num_questions} questions for {loader.name}'
            )
        )
