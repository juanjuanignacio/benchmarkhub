"""
Tests for: python manage.py bm_run <benchmark> <provider> <model> [options]
"""
from unittest.mock import patch

from django.core.management.base import CommandError

from apps.runs.models import BenchmarkRun
from tests.base import BaseCommandTest


MOCK_RUNNER = 'apps.runs.management.commands.bm_run.start_run_in_background'


class TestBmRun(BaseCommandTest):

    def test_creates_run_with_defaults(self):
        with patch(MOCK_RUNNER):
            out = self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2')
        self.assertTrue(BenchmarkRun.objects.filter(model_name='llama3.2').exists())
        self.assertIn('started', out.lower())

    def test_benchmark_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_run', 'no-such-bench', 'test-provider', 'llama3.2')

    def test_benchmark_not_loaded_raises(self):
        from apps.benchmarks.models import Benchmark
        Benchmark.objects.create(slug='unloaded', name='Unloaded', loaded_at=None)
        with self.assertRaises(CommandError):
            self.call('bm_run', 'unloaded', 'test-provider', 'llama3.2')

    def test_provider_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_run', 'test-bench', 'ghost-provider', 'llama3.2')

    def test_run_stores_temperature(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--temperature', '0.7')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertAlmostEqual(run.temperature, 0.7)

    def test_run_stores_max_tokens(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--max-tokens', '1024')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.max_tokens, 1024)

    def test_run_stores_num_questions(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--num-questions', '50')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.num_questions, 50)

    def test_run_stores_system_prompt(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--system-prompt', 'Answer briefly.')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.system_prompt, 'Answer briefly.')

    def test_run_stores_few_shot(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--few-shot', '3')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.few_shot_count, 3)

    def test_run_stores_cot_flag(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2', '--cot')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertTrue(run.use_cot)

    def test_run_stores_tags(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--tags', 'baseline,v1')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertIn('baseline', run.tags)

    def test_run_stores_notes(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--notes', 'First experiment')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.notes, 'First experiment')

    def test_run_workers_minimum_one(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2',
                      '--workers', '0')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.parallel_workers, 1)

    def test_run_starts_background(self):
        with patch(MOCK_RUNNER) as mock_start:
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2')
        mock_start.assert_called_once()

    def test_run_status_is_pending(self):
        with patch(MOCK_RUNNER):
            self.call('bm_run', 'test-bench', 'test-provider', 'llama3.2')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertEqual(run.status, 'pending')
