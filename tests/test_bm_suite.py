"""
Tests for: python manage.py bm_suite list|create|run|delete
"""
from unittest.mock import patch

from django.core.management.base import CommandError

from apps.benchmarks.models import BenchmarkSuite, BenchmarkSuiteItem
from apps.runs.models import BenchmarkRun, BenchmarkSuiteRun
from tests.base import BaseCommandTest, make_benchmark


MOCK_RUNNER = 'apps.runs.management.commands.bm_suite.start_run_in_background'


class TestBmSuiteList(BaseCommandTest):

    def test_list_empty(self):
        out = self.call('bm_suite', 'list')
        self.assertIn('No suites', out)

    def test_list_shows_suites(self):
        suite = BenchmarkSuite.objects.create(slug='s1', name='My Suite')
        BenchmarkSuiteItem.objects.create(suite=suite, benchmark=self.benchmark, order=0)
        out = self.call('bm_suite', 'list')
        self.assertIn('My Suite', out)
        self.assertIn('test-bench', out)


class TestBmSuiteCreate(BaseCommandTest):

    def test_create_suite(self):
        out = self.call('bm_suite', 'create', 'Clinical Suite', 'test-bench')
        self.assertIn('created', out.lower())
        self.assertTrue(BenchmarkSuite.objects.filter(name='Clinical Suite').exists())

    def test_create_suite_with_multiple_benchmarks(self):
        bm2 = make_benchmark(slug='bench2', name='Bench 2')
        out = self.call('bm_suite', 'create', 'Multi Suite', 'test-bench', 'bench2')
        suite = BenchmarkSuite.objects.get(name='Multi Suite')
        self.assertEqual(suite.items.count(), 2)

    def test_create_suite_slug_auto_generated(self):
        self.call('bm_suite', 'create', 'My Test Suite', 'test-bench')
        suite = BenchmarkSuite.objects.get(name='My Test Suite')
        self.assertIn('my', suite.slug)

    def test_create_suite_unknown_benchmark_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_suite', 'create', 'Bad Suite', 'no-such-bench')

    def test_create_suite_rollback_on_bad_benchmark(self):
        """Suite should not be created if any benchmark is invalid."""
        initial_count = BenchmarkSuite.objects.count()
        with self.assertRaises(CommandError):
            self.call('bm_suite', 'create', 'Bad Suite', 'test-bench', 'ghost')
        self.assertEqual(BenchmarkSuite.objects.count(), initial_count)


class TestBmSuiteRun(BaseCommandTest):

    def setUp(self):
        super().setUp()
        self.suite = BenchmarkSuite.objects.create(slug='s1', name='Run Suite')
        BenchmarkSuiteItem.objects.create(suite=self.suite, benchmark=self.benchmark, order=0)

    def test_run_suite_creates_suite_run(self):
        with patch(MOCK_RUNNER):
            out = self.call('bm_suite', 'run', str(self.suite.id),
                            'test-provider', 'llama3.2')
        self.assertTrue(BenchmarkSuiteRun.objects.filter(suite=self.suite).exists())

    def test_run_suite_creates_benchmark_runs(self):
        with patch(MOCK_RUNNER):
            self.call('bm_suite', 'run', str(self.suite.id),
                      'test-provider', 'llama3.2')
        self.assertTrue(
            BenchmarkRun.objects.filter(suite_run__suite=self.suite).exists()
        )

    def test_run_suite_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_suite', 'run', '99999', 'test-provider', 'llama3.2')

    def test_run_suite_provider_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_suite', 'run', str(self.suite.id), 'ghost', 'llama3.2')

    def test_run_skips_unloaded_benchmarks(self):
        bm2 = make_benchmark(slug='unloaded-bm', name='Unloaded', loaded=False)
        BenchmarkSuiteItem.objects.create(suite=self.suite, benchmark=bm2, order=1)
        with patch(MOCK_RUNNER):
            out = self.call('bm_suite', 'run', str(self.suite.id),
                            'test-provider', 'llama3.2')
        self.assertIn('Skipping', out)
        # Only 1 run created (the loaded one)
        self.assertEqual(
            BenchmarkRun.objects.filter(suite_run__suite=self.suite).count(), 1
        )

    def test_run_calls_background_runner(self):
        with patch(MOCK_RUNNER) as mock_start:
            self.call('bm_suite', 'run', str(self.suite.id),
                      'test-provider', 'llama3.2')
        mock_start.assert_called_once()


class TestBmSuiteDelete(BaseCommandTest):

    def test_delete_suite(self):
        suite = BenchmarkSuite.objects.create(slug='del-suite', name='Delete Me')
        out = self.call('bm_suite', 'delete', str(suite.id))
        self.assertIn('deleted', out.lower())
        self.assertFalse(BenchmarkSuite.objects.filter(id=suite.id).exists())

    def test_delete_nonexistent_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_suite', 'delete', '99999')
