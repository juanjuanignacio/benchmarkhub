"""
Import pre-computed model answers from a CSV file to create a scored run.

The CSV must have at minimum:
    question_id, answer

Optionally:
    is_correct   (true/false — recalculated if missing)

Examples:
    python manage.py bm_import_results mmlu results.csv --model gpt-4o-external
    python manage.py bm_import_results rag_bench answers.csv --model my-pipeline --provider csv-import
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from apps.runs.models import BenchmarkRun, RunResult


class Command(BaseCommand):
    help = 'Import pre-computed model answers from CSV to create a scored run'

    def add_arguments(self, parser):
        parser.add_argument('benchmark', help='Benchmark slug')
        parser.add_argument('csv_file', help='Path to CSV file with results')
        parser.add_argument('--model', required=True,
                            help='Model name label for this run (e.g. gpt-4o-external)')
        parser.add_argument('--provider', default='csv-import',
                            help='Provider slug (default: csv-import)')
        parser.add_argument('--notes', default='',
                            help='Notes for this run')
        parser.add_argument('--tags', default='imported',
                            help='Tags (default: imported)')

    def handle(self, *args, **options):
        try:
            benchmark = Benchmark.objects.get(slug=options['benchmark'])
        except Benchmark.DoesNotExist:
            raise CommandError(f"Benchmark '{options['benchmark']}' not found.")

        # Get or create a dummy provider for CSV imports
        from apps.providers.models import Provider
        provider, _ = Provider.objects.get_or_create(
            slug=options['provider'],
            defaults={
                'name': 'CSV Import',
                'provider_type': 'openai',
                'base_url': 'http://localhost',
                'is_active': False,
            },
        )

        # Read CSV
        try:
            with open(options['csv_file'], newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['csv_file']}")

        if not rows:
            raise CommandError('CSV file is empty.')

        required = {'question_id', 'answer'}
        missing = required - set(rows[0].keys())
        if missing:
            raise CommandError(
                f"CSV is missing required columns: {missing}. "
                f"Required: question_id, answer"
            )

        # Create run
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            provider=provider,
            model_name=options['model'],
            status='completed',
            total_questions=0,
            tags=options['tags'],
            notes=options['notes'],
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        imported = 0
        skipped = 0
        correct = 0

        for row in rows:
            qid = str(row['question_id']).strip()
            answer = row['answer'].strip()

            try:
                question = BenchmarkQuestion.objects.get(benchmark=benchmark, question_id=qid)
            except BenchmarkQuestion.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'  Question {qid} not found — skipped')
                )
                skipped += 1
                continue

            # Evaluate if is_correct not provided
            if 'is_correct' in row and row['is_correct'].lower() in ('true', '1', 'yes'):
                is_correct = True
            elif 'is_correct' in row and row['is_correct'].lower() in ('false', '0', 'no'):
                is_correct = False
            else:
                # Simple normalised comparison
                is_correct = (
                    answer.strip().lower() == question.correct_answer.strip().lower()
                )

            RunResult.objects.create(
                run=run,
                question=question,
                model_response=answer,
                parsed_answer=answer,
                is_correct=is_correct,
                response_time=0.0,
            )
            imported += 1
            if is_correct:
                correct += 1

        run.total_questions = imported
        run.correct_answers = correct
        run.score = (correct / imported * 100) if imported else 0.0
        run.save(update_fields=['total_questions', 'correct_answers', 'score'])

        self.stdout.write(self.style.SUCCESS(
            f'\nRun #{run.id} created — '
            f'{correct}/{imported} correct = {run.score:.1f}%'
        ))
        if skipped:
            self.stdout.write(self.style.WARNING(f'  {skipped} rows skipped (question_id not found)'))
