"""
Tests for: python manage.py bm_create <slug> <name> <csv_file> [options]
"""
import csv
import os
import tempfile

from django.core.management.base import CommandError

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from tests.base import BaseCommandTest


def write_benchmark_csv(path, rows):
    if not rows:
        open(path, 'w').close()
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


MINIMAL_ROWS = [
    {'question': 'What is 2+2?', 'correct_answer': '4'},
    {'question': 'Capital of France?', 'correct_answer': 'Paris'},
]

FULL_ROWS = [
    {
        'question': 'What is 2+2?',
        'correct_answer': 'A',
        'choice_a': '4', 'choice_b': '3', 'choice_c': '5', 'choice_d': '6',
        'subject': 'Math', 'difficulty': 'easy',
    },
]


class TestBmCreate(BaseCommandTest):

    def _tempcsv(self, rows):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_benchmark_csv(f.name, rows)
        return f.name

    def test_creates_benchmark_and_questions(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            out = self.call('bm_create', 'new-bm', 'New Benchmark', path)
            self.assertIn('created', out.lower())
            self.assertTrue(Benchmark.objects.filter(slug='new-bm').exists())
            self.assertEqual(
                BenchmarkQuestion.objects.filter(benchmark__slug='new-bm').count(), 2
            )
        finally:
            os.unlink(path)

    def test_creates_with_full_mcq_columns(self):
        path = self._tempcsv(FULL_ROWS)
        try:
            self.call('bm_create', 'mcq-bm', 'MCQ Benchmark', path)
            q = BenchmarkQuestion.objects.get(benchmark__slug='mcq-bm')
            self.assertEqual(q.choice_a, '4')
            self.assertEqual(q.subject, 'Math')
            self.assertEqual(q.difficulty, 'easy')
        finally:
            os.unlink(path)

    def test_invalid_slug_raises(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            with self.assertRaises(CommandError):
                self.call('bm_create', 'Bad Slug!', 'Name', path)
        finally:
            os.unlink(path)

    def test_duplicate_slug_raises(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            with self.assertRaises(CommandError):
                # 'test-bench' already exists from setUp
                self.call('bm_create', 'test-bench', 'Dup', path)
        finally:
            os.unlink(path)

    def test_force_overwrites_existing(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            out = self.call('bm_create', 'test-bench', 'Updated Bench', path, '--force')
            bm = Benchmark.objects.get(slug='test-bench')
            self.assertEqual(bm.name, 'Updated Bench')
            self.assertEqual(bm.questions.count(), 2)
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_create', 'new-bm', 'Name', '/no/such/file.csv')

    def test_empty_csv_raises(self):
        path = self._tempcsv([])
        try:
            with self.assertRaises(CommandError):
                self.call('bm_create', 'empty-bm', 'Empty', path)
        finally:
            os.unlink(path)

    def test_missing_required_columns_raises(self):
        path = self._tempcsv([{'wrong_col': 'x'}])
        try:
            with self.assertRaises(CommandError):
                self.call('bm_create', 'bad-cols', 'Bad', path)
        finally:
            os.unlink(path)

    def test_custom_category(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_create', 'cat-bm', 'Cat Benchmark', path,
                      '--category', 'biomedical')
            bm = Benchmark.objects.get(slug='cat-bm')
            self.assertEqual(bm.category, 'biomedical')
        finally:
            os.unlink(path)

    def test_loaded_at_set(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_create', 'loaded-bm', 'Loaded', path)
            bm = Benchmark.objects.get(slug='loaded-bm')
            self.assertIsNotNone(bm.loaded_at)
        finally:
            os.unlink(path)

    def test_num_questions_updated(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_create', 'count-bm', 'Count Benchmark', path)
            bm = Benchmark.objects.get(slug='count-bm')
            self.assertEqual(bm.num_questions, 2)
        finally:
            os.unlink(path)
