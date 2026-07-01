"""
Create a RAG benchmark from a CSV file.

Required CSV columns: context, question, correct_answer
Optional columns:     subject, difficulty
The correct_answer field supports pipe-separated aliases: e.g. "Paris|City of Light"

Examples:
    python manage.py bm_import_rag clinical-rag "Clinical Notes QA" notes_qa.csv
    python manage.py bm_import_rag pubmed-rag "PubMed QA" pubmed_qa.csv --category biomedical
"""
import csv
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion


class Command(BaseCommand):
    help = 'Create a RAG benchmark from a CSV file (context + question + answer)'

    def add_arguments(self, parser):
        parser.add_argument('slug', help='URL-friendly slug (e.g. clinical-rag)')
        parser.add_argument('name', help='Human-readable benchmark name')
        parser.add_argument('csv_file', help='Path to CSV file')
        parser.add_argument('--category', default='rag',
                            help='Category (default: rag)')
        parser.add_argument('--description', default='',
                            help='Optional description')
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing benchmark with same slug')

    def handle(self, *args, **options):
        slug = options['slug']
        if not re.match(r'^[a-z0-9][a-z0-9\-]*$', slug):
            raise CommandError(
                f"Slug '{slug}' is invalid. Use only lowercase letters, digits, and hyphens."
            )

        existing = Benchmark.objects.filter(slug=slug).first()
        if existing and not options['force']:
            raise CommandError(
                f"Benchmark '{slug}' already exists. Use --force to overwrite."
            )

        try:
            with open(options['csv_file'], newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['csv_file']}")

        if not rows:
            raise CommandError('CSV file is empty.')

        required = {'context', 'question', 'correct_answer'}
        missing = required - set(rows[0].keys())
        if missing:
            raise CommandError(
                f"CSV missing required columns: {missing}. "
                f"Required: context, question, correct_answer"
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
                    metadata={'is_rag': True, 'is_custom': True},
                )

            batch = []
            for idx, row in enumerate(rows):
                batch.append(BenchmarkQuestion(
                    benchmark=benchmark,
                    question_id=str(row.get('question_id', idx + 1)),
                    question=row['question'],
                    correct_answer=row['correct_answer'],
                    context=row['context'],
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
            f'RAG benchmark "{benchmark.name}" created — '
            f'{benchmark.num_questions} questions (slug: {slug})'
        ))
