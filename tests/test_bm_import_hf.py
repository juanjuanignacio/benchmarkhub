"""
Tests for: python manage.py bm_import_hf <dataset> [config] --name <name> [options]
"""
from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError

from apps.benchmarks.models import Benchmark, BenchmarkQuestion
from tests.base import BaseCommandTest


def _make_mock_dataset(items):
    """Return a mock HuggingFace dataset object."""
    mock_ds = MagicMock()
    mock_ds.column_names = list(items[0].keys()) if items else []
    mock_ds.__iter__ = MagicMock(return_value=iter(items))
    mock_ds.__len__ = MagicMock(return_value=len(items))
    # select() returns a new smaller dataset
    mock_ds.select = MagicMock(return_value=mock_ds)
    return mock_ds


SAMPLE_ITEMS = [
    {
        'question': 'What is the capital of France?',
        'answer': 'Paris',
        'subject': 'Geography',
    },
    {
        'question': 'What is 2+2?',
        'answer': '4',
        'subject': 'Math',
    },
]

MCQ_ITEMS = [
    {
        'question': 'Which planet is largest?',
        'choices': ['Mars', 'Jupiter', 'Earth', 'Venus'],
        'answer': 1,  # index → B
        'subject': 'Science',
    },
]


class TestBmImportHF(BaseCommandTest):

    def _call_with_mock(self, dataset_items, *args, **kwargs):
        mock_ds = _make_mock_dataset(dataset_items)
        # load_dataset is imported lazily inside handle(), so patch at source
        with patch('datasets.load_dataset', return_value=mock_ds):
            return self.call('bm_import_hf', *args, **kwargs)

    # ── Happy path ──────────────────────────────────────────────────────────

    def test_basic_import_auto_detect(self):
        out = self._call_with_mock(
            SAMPLE_ITEMS,
            'openai/some-dataset', '--name', 'My Dataset',
        )
        self.assertIn('created', out.lower())
        self.assertTrue(Benchmark.objects.filter(name='My Dataset').exists())

    def test_questions_created(self):
        self._call_with_mock(
            SAMPLE_ITEMS,
            'openai/some-dataset', '--name', 'Q Dataset',
        )
        bm = Benchmark.objects.get(name='Q Dataset')
        self.assertEqual(bm.questions.count(), 2)

    def test_subject_stored(self):
        self._call_with_mock(
            SAMPLE_ITEMS,
            'openai/some-dataset', '--name', 'Subj Dataset',
        )
        bm = Benchmark.objects.get(name='Subj Dataset')
        subjects = set(bm.questions.values_list('subject', flat=True))
        self.assertIn('Geography', subjects)

    def test_mcq_numeric_answer_converted_to_letter(self):
        """Answer index 1 → letter B."""
        self._call_with_mock(
            MCQ_ITEMS,
            'test/mcq', '--name', 'MCQ Dataset',
            '--question-col', 'question',
            '--answer-col', 'answer',
        )
        bm = Benchmark.objects.get(name='MCQ Dataset')
        q = bm.questions.first()
        self.assertEqual(q.correct_answer, 'B')

    def test_samples_limit(self):
        items = [{'question': f'Q{i}', 'answer': str(i)} for i in range(10)]
        mock_ds = _make_mock_dataset(items)
        limited_ds = _make_mock_dataset(items[:3])
        mock_ds.select = MagicMock(return_value=limited_ds)
        with patch('datasets.load_dataset', return_value=mock_ds):
            self.call('bm_import_hf', 'test/data', '--name', 'Limited', '--samples', '3')
        bm = Benchmark.objects.get(name='Limited')
        self.assertEqual(bm.questions.count(), 3)

    def test_slug_auto_generated(self):
        self._call_with_mock(
            SAMPLE_ITEMS,
            'test/data', '--name', 'Auto Slug Bench',
        )
        self.assertTrue(Benchmark.objects.filter(slug='auto-slug-bench').exists())

    def test_custom_slug(self):
        self._call_with_mock(
            SAMPLE_ITEMS,
            'test/data', '--name', 'Custom', '--slug', 'my-custom-slug',
        )
        self.assertTrue(Benchmark.objects.filter(slug='my-custom-slug').exists())

    # ── Error cases ─────────────────────────────────────────────────────────

    def test_duplicate_slug_raises(self):
        with self.assertRaises(CommandError):
            self._call_with_mock(
                SAMPLE_ITEMS,
                'test/data', '--name', 'Test Benchmark',
                '--slug', 'test-bench',  # already exists from setUp
            )

    def test_force_overwrites(self):
        self._call_with_mock(
            SAMPLE_ITEMS,
            'test/data', '--name', 'Test Benchmark',
            '--slug', 'test-bench', '--force',
        )
        bm = Benchmark.objects.get(slug='test-bench')
        self.assertEqual(bm.name, 'Test Benchmark')

    def test_load_dataset_failure_raises(self):
        with patch('datasets.load_dataset', side_effect=Exception('network error')):
            with self.assertRaises(CommandError):
                self.call('bm_import_hf', 'bad/dataset', '--name', 'Bad')

    def test_undetectable_question_col_raises(self):
        items = [{'foo': 'x', 'bar': 'y'}]  # no recognisable column names
        with self.assertRaises(CommandError):
            self._call_with_mock(items, 'test/data', '--name', 'Bad Cols')

    def test_explicit_column_mapping(self):
        items = [{'q': 'What?', 'a': 'Yes', 'cat': 'Logic'}]
        self._call_with_mock(
            items,
            'test/data', '--name', 'Mapped',
            '--question-col', 'q',
            '--answer-col', 'a',
            '--subject-col', 'cat',
        )
        bm = Benchmark.objects.get(name='Mapped')
        q = bm.questions.first()
        self.assertEqual(q.question, 'What?')
        self.assertEqual(q.correct_answer, 'Yes')
        self.assertEqual(q.subject, 'Logic')

    def test_loaded_at_set(self):
        self._call_with_mock(SAMPLE_ITEMS, 'test/data', '--name', 'Loaded HF')
        bm = Benchmark.objects.get(name='Loaded HF')
        self.assertIsNotNone(bm.loaded_at)
