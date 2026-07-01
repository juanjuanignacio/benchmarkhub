"""
Tests for: python manage.py bm_import_results <benchmark> <csv_file> --model <name>
"""
import csv
import os
import tempfile

from django.core.management.base import CommandError

from apps.runs.models import BenchmarkRun, RunResult
from tests.base import BaseCommandTest


def write_csv(path, rows, headers=None):
    if headers is None:
        headers = list(rows[0].keys()) if rows else []
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class TestBmImportResults(BaseCommandTest):

    def _csv_with_correct_answers(self):
        """Return a temp CSV path with answers matching the benchmark questions."""
        questions = list(self.benchmark.questions.all())
        rows = [
            {'question_id': q.question_id, 'answer': q.correct_answer}
            for q in questions
        ]
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, rows)
        return f.name

    def test_basic_import(self):
        path = self._csv_with_correct_answers()
        try:
            out = self.call('bm_import_results', 'test-bench', path, '--model', 'my-model')
            self.assertIn('Run #', out)
            self.assertTrue(BenchmarkRun.objects.filter(model_name='my-model').exists())
        finally:
            os.unlink(path)

    def test_score_calculated_correctly(self):
        """All answers correct → 100% score."""
        path = self._csv_with_correct_answers()
        try:
            self.call('bm_import_results', 'test-bench', path, '--model', 'perfect-model')
            run = BenchmarkRun.objects.get(model_name='perfect-model')
            self.assertAlmostEqual(run.score, 100.0)
            self.assertEqual(run.correct_answers, 3)
        finally:
            os.unlink(path)

    def test_wrong_answers_scored(self):
        questions = list(self.benchmark.questions.all())
        rows = [
            {'question_id': q.question_id, 'answer': 'Z'}  # All wrong
            for q in questions
        ]
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, rows)
        try:
            self.call('bm_import_results', 'test-bench', f.name, '--model', 'bad-model')
            run = BenchmarkRun.objects.get(model_name='bad-model')
            self.assertAlmostEqual(run.score, 0.0)
        finally:
            os.unlink(f.name)

    def test_is_correct_column_respected(self):
        questions = list(self.benchmark.questions.all())
        rows = [
            {'question_id': q.question_id, 'answer': 'X', 'is_correct': 'true'}
            for q in questions
        ]
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, rows)
        try:
            self.call('bm_import_results', 'test-bench', f.name, '--model', 'forced-model')
            run = BenchmarkRun.objects.get(model_name='forced-model')
            # is_correct=true forced even though answers are wrong
            self.assertAlmostEqual(run.score, 100.0)
        finally:
            os.unlink(f.name)

    def test_benchmark_not_found_raises(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, [{'question_id': '1', 'answer': 'A'}])
        try:
            with self.assertRaises(CommandError):
                self.call('bm_import_results', 'ghost-bench', f.name, '--model', 'x')
        finally:
            os.unlink(f.name)

    def test_file_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_import_results', 'test-bench', '/no/such/file.csv',
                      '--model', 'x')

    def test_missing_columns_raises(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, [{'wrong_col': '1'}])
        try:
            with self.assertRaises(CommandError):
                self.call('bm_import_results', 'test-bench', f.name, '--model', 'x')
        finally:
            os.unlink(f.name)

    def test_unknown_question_id_skipped(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_csv(f.name, [{'question_id': '99999', 'answer': 'A'}])
        try:
            out = self.call('bm_import_results', 'test-bench', f.name, '--model', 'skip-model')
            self.assertIn('skipped', out.lower())
        finally:
            os.unlink(f.name)

    def test_run_status_is_completed(self):
        path = self._csv_with_correct_answers()
        try:
            self.call('bm_import_results', 'test-bench', path, '--model', 'done-model')
            run = BenchmarkRun.objects.get(model_name='done-model')
            self.assertEqual(run.status, 'completed')
        finally:
            os.unlink(path)

    def test_tags_and_notes_stored(self):
        path = self._csv_with_correct_answers()
        try:
            self.call('bm_import_results', 'test-bench', path, '--model', 'tagged-model',
                      '--tags', 'external', '--notes', 'from CSV')
            run = BenchmarkRun.objects.get(model_name='tagged-model')
            self.assertIn('external', run.tags)
            self.assertEqual(run.notes, 'from CSV')
        finally:
            os.unlink(path)

    def test_creates_provider_if_not_exists(self):
        from apps.providers.models import Provider
        path = self._csv_with_correct_answers()
        try:
            self.call('bm_import_results', 'test-bench', path,
                      '--model', 'ext-model', '--provider', 'new-csv-provider')
            self.assertTrue(Provider.objects.filter(slug='new-csv-provider').exists())
        finally:
            os.unlink(path)
