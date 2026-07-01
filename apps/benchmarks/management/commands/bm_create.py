"""
Create a custom benchmark from a CSV file.

Required CSV columns: question, correct_answer
Optional columns:     choice_a, choice_b, choice_c, choice_d, subject, difficulty

Examples:
    python manage.py bm_create my-benchmark "My Benchmark" questions.csv
    python manage.py bm_create clinical-qa "Clinical QA" data.csv --category clinical
"""
import csv
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion


class Command(BaseCommand):
    help = 'Create a custom benchmark from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('slug', help='URL-friendly slug (e.g. my-benchmark)')
        parser.add_argument('name', help='Human-readable benchmark name')
        parser.add_argument('csv_file', help='Path to the CSV file')
        parser.add_argument('--category', default='custom',
                            help='Category label (default: custom)')
        parser.add_argument('--description', default='',
                            help='Optional description')
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing benchmark with the same slug')

    def handle(self, *args, **options):
        slug = options['slug']
        if not re.match(r'^[a-z0-9][a-z0-9\-]*$', slug):
            raise CommandError(
                f"Slug '{slug}' is invalid. Use only lowercase letters, digits, and hyphens."
            )

        existing = Benchmark.objects.filter(slug=slug).first()
        if existing and not options['force']:
            raise CommandError(
                f"Benchmark '{slug}' already exists "
                f"({existing.num_questions} questions). Use --force to overwrite."
            )

        try:
            with open(options['csv_file'], newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['csv_file']}")

        if not rows:
            raise CommandError('CSV file is empty.')

        missing = {'question', 'correct_answer'} - set(rows[0].keys())
        if missing:
            raise CommandError(
                f"CSV missing required columns: {missing}. "
                f"Required: question, correct_answer"
            )

        with transaction.atomic():
            if existing:
                BenchmarkQuestion.objects.filter(benchmark=existing).delete()
                benchmark = existing
                benchmark.name = options['name']
                benchmark.description = options['description']
                benchmark.category = options['category']
            else:
                benchmark = Benchmark.objects.create(
                    slug=slug,
                    name=options['name'],
                    description=options['description'],
                    category=options['category'],
                    metadata={'is_custom': True},
                )

            batch = []
            for idx, row in enumerate(rows):
                batch.append(BenchmarkQuestion(
                    benchmark=benchmark,
                    question_id=str(row.get('question_id', idx + 1)),
                    question=row['question'],
                    correct_answer=row['correct_answer'],
                    choice_a=row.get('choice_a', ''),
                    choice_b=row.get('choice_b', ''),
                    choice_c=row.get('choice_c', ''),
                    choice_d=row.get('choice_d', ''),
                    subject=row.get('subject', row.get('category', '')),
                    difficulty=row.get('difficulty', ''),
                ))
                if len(batch) >= 500:
                    BenchmarkQuestion.objects.bulk_create(batch, ignore_conflicts=True)
                    batch = []
            if batch:
                BenchmarkQuestion.objects.bulk_create(batch, ignore_conflicts=True)

            benchmark.num_questions = BenchmarkQuestion.objects.filter(benchmark=benchmark).count()
            benchmark.loaded_at = timezone.now()
            benchmark.save()

        self.stdout.write(self.style.SUCCESS(
            f'Benchmark "{benchmark.name}" created — '
            f'{benchmark.num_questions} questions loaded (slug: {slug})'
        ))
