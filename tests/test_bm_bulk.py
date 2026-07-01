"""
Tests for: python manage.py bm_bulk BENCHMARK_OR_MODEL... [options]
"""
from unittest.mock import patch

from django.core.management.base import CommandError

from apps.runs.models import BenchmarkRun
from tests.base import BaseCommandTest, make_benchmark


MOCK_RUNNER = 'apps.runs.management.commands.bm_bulk.start_run_in_background'


class TestBmBulk(BaseCommandTest):

    def test_creates_run_for_each_model(self):
        p2 = self._add_provider('provider2')
        with patch(MOCK_RUNNER):
            out = self.call('bm_bulk', 'test-bench',
                            'test-provider/llama3.2',
                            'provider2/gpt-4o')
        runs = BenchmarkRun.objects.filter(benchmark=self.benchmark)
        self.assertEqual(runs.count(), 2)
        models = set(runs.values_list('model_name', flat=True))
        self.assertIn('llama3.2', models)
        self.assertIn('gpt-4o', models)

    def test_creates_runs_for_each_benchmark_x_model(self):
        bm2 = make_benchmark(slug='bench2', name='Bench 2')
        with patch(MOCK_RUNNER):
            self.call('bm_bulk', 'test-bench', 'bench2', 'test-provider/llama3.2')
        runs = BenchmarkRun.objects.filter(model_name='llama3.2')
        self.assertEqual(runs.count(), 2)

    def test_no_benchmark_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'test-provider/llama3.2')

    def test_no_model_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'test-bench')

    def test_unknown_benchmark_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'no-such', 'test-provider/llama3.2')

    def test_unknown_provider_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'test-bench', 'ghost/llama3.2')

    def test_invalid_model_spec_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'test-bench', 'badspec-no-slash')

    def test_bulk_tag_applied(self):
        with patch(MOCK_RUNNER):
            self.call('bm_bulk', 'test-bench', 'test-provider/llama3.2')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertIn('bulk_', run.tags)

    def test_custom_tag_preserved(self):
        with patch(MOCK_RUNNER):
            self.call('bm_bulk', 'test-bench', 'test-provider/llama3.2',
                      '--tags', 'myexp')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertIn('myexp', run.tags)

    def test_options_stored(self):
        with patch(MOCK_RUNNER):
            self.call('bm_bulk', 'test-bench', 'test-provider/llama3.2',
                      '--temperature', '0.5', '--num-questions', '100')
        run = BenchmarkRun.objects.get(model_name='llama3.2')
        self.assertAlmostEqual(run.temperature, 0.5)
        self.assertEqual(run.num_questions, 100)

    def test_unloaded_benchmark_raises(self):
        from apps.benchmarks.models import Benchmark
        Benchmark.objects.create(slug='unloaded', name='Unloaded', loaded_at=None)
        with self.assertRaises(CommandError):
            self.call('bm_bulk', 'unloaded', 'test-provider/llama3.2')

    def _add_provider(self, slug):
        from apps.providers.models import Provider
        return Provider.objects.create(
            slug=slug, name=slug, provider_type='openai', is_active=True,
        )
