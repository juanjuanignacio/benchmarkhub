"""
Import a benchmark from HuggingFace Hub.

Examples:
    python manage.py bm_import_hf cais/mmlu anatomy --split test --name "MMLU Anatomy"
    python manage.py bm_import_hf openai/gsm8k main --split test --name "GSM8K" \\
        --question-col question --answer-col answer
    python manage.py bm_import_hf bigbio/med_qa bigbio_qa --split test \\
        --name "MedQA" --samples 500
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion


class Command(BaseCommand):
    help = 'Import a benchmark from HuggingFace Hub'

    def add_arguments(self, parser):
        parser.add_argument('dataset', help='HuggingFace dataset ID (e.g. cais/mmlu)')
        parser.add_argument('config', nargs='?', default=None,
                            help='Dataset configuration / subset name (e.g. anatomy)')
        parser.add_argument('--split', default='test',
                            help='Dataset split to load (default: test)')
        parser.add_argument('--name', required=True,
                            help='Benchmark name')
        parser.add_argument('--slug', default='',
                            help='Benchmark slug (auto-generated from name if omitted)')
        parser.add_argument('--category', default='imported',
                            help='Category label (default: imported)')
        parser.add_argument('--samples', type=int, default=0,
                            help='Max questions to import (0 = all)')
        parser.add_argument('--question-col', default='',
                            help='Column name for question text (auto-detected if omitted)')
        parser.add_argument('--answer-col', default='',
                            help='Column name for correct answer (auto-detected if omitted)')
        parser.add_argument('--subject-col', default='',
                            help='Column name for subject/category (optional)')
        parser.add_argument('--choice-a', default='', help='Column for choice A')
        parser.add_argument('--choice-b', default='', help='Column for choice B')
        parser.add_argument('--choice-c', default='', help='Column for choice C')
        parser.add_argument('--choice-d', default='', help='Column for choice D')
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing benchmark with same slug')

    def handle(self, *args, **options):
        try:
            from datasets import load_dataset
        except ImportError:
            raise CommandError(
                'HuggingFace datasets library is required: pip install datasets'
            )

        import re
        slug = options['slug'] or re.sub(
            r'[^a-z0-9]+', '-',
            options['name'].lower()
        ).strip('-')

        existing = Benchmark.objects.filter(slug=slug).first()
        if existing and not options['force']:
            raise CommandError(
                f"Benchmark '{slug}' already exists. Use --force to overwrite."
            )

        self.stdout.write(
            f'Loading {options["dataset"]} '
            f'(config={options["config"]}, split={options["split"]})...'
        )
        try:
            ds = load_dataset(
                options['dataset'],
                options['config'],
                split=options['split'],
                trust_remote_code=True,
            )
        except Exception as e:
            raise CommandError(f'Failed to load dataset: {e}')

        if options['samples']:
            ds = ds.select(range(min(options['samples'], len(ds))))

        # Auto-detect columns
        cols = ds.column_names
        self.stdout.write(f'  Columns: {cols}')

        q_col = options['question_col'] or self._detect(cols, ['question', 'input', 'text', 'prompt'])
        a_col = options['answer_col'] or self._detect(cols, ['answer', 'correct_answer', 'target', 'label', 'output'])
        s_col = options['subject_col'] or self._detect(cols, ['subject', 'category', 'type', 'task'], required=False)

        if not q_col:
            raise CommandError(
                f'Cannot auto-detect question column. Specify with --question-col. '
                f'Available: {cols}'
            )
        if not a_col:
            raise CommandError(
                f'Cannot auto-detect answer column. Specify with --answer-col. '
                f'Available: {cols}'
            )

        self.stdout.write(f'  Using: question={q_col}, answer={a_col}, subject={s_col}')

        # MCQ choice columns
        choice_map = {
            'choice_a': options['choice_a'] or self._detect(cols, ['A', 'choice_a', 'option_a', 'choices'], required=False),
            'choice_b': options['choice_b'] or self._detect(cols, ['B', 'choice_b', 'option_b'], required=False),
            'choice_c': options['choice_c'] or self._detect(cols, ['C', 'choice_c', 'option_c'], required=False),
            'choice_d': options['choice_d'] or self._detect(cols, ['D', 'choice_d', 'option_d'], required=False),
        }

        with transaction.atomic():
            if existing:
                BenchmarkQuestion.objects.filter(benchmark=existing).delete()
                benchmark = existing
                benchmark.name = options['name']
                benchmark.category = options['category']
            else:
                benchmark = Benchmark.objects.create(
                    slug=slug,
                    name=options['name'],
                    category=options['category'],
                    metadata={
                        'source': options['dataset'],
                        'config': options['config'],
                        'split': options['split'],
                    },
                )

            batch = []
            for idx, item in enumerate(ds):
                # Handle choices field (list)
                choices = {}
                for key, col in choice_map.items():
                    if col and col in item:
                        val = item[col]
                        if isinstance(val, list) and key == 'choice_a':
                            # choices is a list field
                            if len(val) > 0: choices['choice_a'] = str(val[0])
                            if len(val) > 1: choices['choice_b'] = str(val[1])
                            if len(val) > 2: choices['choice_c'] = str(val[2])
                            if len(val) > 3: choices['choice_d'] = str(val[3])
                            break
                        else:
                            choices[key] = str(val)

                answer = item[a_col]
                # Convert numeric answer index to letter for MCQ
                if isinstance(answer, int) and 'choice_a' in choices:
                    answer = chr(ord('A') + answer)

                batch.append(BenchmarkQuestion(
                    benchmark=benchmark,
                    question_id=str(item.get('id', idx + 1)),
                    question=str(item[q_col]),
                    correct_answer=str(answer),
                    subject=str(item.get(s_col, '')) if s_col else '',
                    **{k: str(v) for k, v in choices.items()},
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
        self.stdout.write(self.style.SUCCESS(
            f'Benchmark "{benchmark.name}" created — '
            f'{benchmark.num_questions} questions (slug: {slug})'
        ))

    @staticmethod
    def _detect(cols, candidates, required=True):
        for c in candidates:
            if c in cols:
                return c
        # Case-insensitive fallback
        cols_lower = {c.lower(): c for c in cols}
        for c in candidates:
            if c.lower() in cols_lower:
                return cols_lower[c.lower()]
        return None if not required else ''
