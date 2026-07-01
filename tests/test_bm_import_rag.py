"""
Tests for: python manage.py bm_import_rag <slug> <name> <csv_file> [options]
"""
import csv
import os
import tempfile

from django.core.management.base import CommandError

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from tests.base import BaseCommandTest


def write_rag_csv(path, rows):
    if not rows:
        open(path, 'w').close()
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


MINIMAL_ROWS = [
    {
        'context': 'Paris is the capital of France.',
        'question': 'What is the capital of France?',
        'correct_answer': 'Paris',
    },
    {
        'context': 'The Earth orbits the Sun.',
        'question': 'What does the Earth orbit?',
        'correct_answer': 'The Sun',
    },
]

FULL_ROWS = [
    {
        'context': 'Paris is the capital of France.',
        'question': 'What is the capital of France?',
        'correct_answer': 'Paris',
        'subject': 'Geography',
        'difficulty': 'easy',
    },
]


class TestBmImportRag(BaseCommandTest):

    def _tempcsv(self, rows):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.close()
        write_rag_csv(f.name, rows)
        return f.name

    def test_creates_benchmark_and_questions(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            out = self.call('bm_import_rag', 'my-rag', 'My RAG', path)
            self.assertIn('created', out.lower())
            self.assertTrue(Benchmark.objects.filter(slug='my-rag').exists())
            self.assertEqual(
                BenchmarkQuestion.objects.filter(benchmark__slug='my-rag').count(), 2
            )
        finally:
            os.unlink(path)

    def test_context_stored(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'rag-ctx', 'RAG Ctx', path)
            q = BenchmarkQuestion.objects.filter(benchmark__slug='rag-ctx').first()
            self.assertIn('Paris', q.context)
        finally:
            os.unlink(path)

    def test_subject_and_difficulty_stored(self):
        path = self._tempcsv(FULL_ROWS)
        try:
            self.call('bm_import_rag', 'rag-full', 'RAG Full', path)
            q = BenchmarkQuestion.objects.get(benchmark__slug='rag-full')
            self.assertEqual(q.subject, 'Geography')
            self.assertEqual(q.difficulty, 'easy')
        finally:
            os.unlink(path)

    def test_invalid_slug_raises(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            with self.assertRaises(CommandError):
                self.call('bm_import_rag', 'Bad Slug!', 'Name', path)
        finally:
            os.unlink(path)

    def test_duplicate_slug_raises(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'rag-dup', 'RAG Dup', path)
            with self.assertRaises(CommandError):
                self.call('bm_import_rag', 'rag-dup', 'RAG Dup 2', path)
        finally:
            os.unlink(path)

    def test_force_overwrites(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'rag-force', 'RAG Force v1', path)
            self.call('bm_import_rag', 'rag-force', 'RAG Force v2', path, '--force')
            bm = Benchmark.objects.get(slug='rag-force')
            self.assertEqual(bm.name, 'RAG Force v2')
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_import_rag', 'no-file', 'No File', '/no/such/file.csv')

    def test_empty_csv_raises(self):
        path = self._tempcsv([])
        try:
            with self.assertRaises(CommandError):
                self.call('bm_import_rag', 'empty-rag', 'Empty', path)
        finally:
            os.unlink(path)

    def test_missing_required_columns_raises(self):
        path = self._tempcsv([{'question': 'Q', 'correct_answer': 'A'}])
        # Missing 'context'
        try:
            with self.assertRaises(CommandError):
                self.call('bm_import_rag', 'bad-cols', 'Bad Cols', path)
        finally:
            os.unlink(path)

    def test_custom_category(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'bio-rag', 'Bio RAG', path,
                      '--category', 'biomedical')
            bm = Benchmark.objects.get(slug='bio-rag')
            self.assertEqual(bm.category, 'biomedical')
        finally:
            os.unlink(path)

    def test_is_rag_flag_in_metadata(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'meta-rag', 'Meta RAG', path)
            bm = Benchmark.objects.get(slug='meta-rag')
            self.assertTrue(bm.metadata.get('is_rag'))
        finally:
            os.unlink(path)

    def test_loaded_at_set(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'loaded-rag', 'Loaded RAG', path)
            bm = Benchmark.objects.get(slug='loaded-rag')
            self.assertIsNotNone(bm.loaded_at)
        finally:
            os.unlink(path)

    def test_num_questions_updated(self):
        path = self._tempcsv(MINIMAL_ROWS)
        try:
            self.call('bm_import_rag', 'count-rag', 'Count RAG', path)
            bm = Benchmark.objects.get(slug='count-rag')
            self.assertEqual(bm.num_questions, 2)
        finally:
            os.unlink(path)
