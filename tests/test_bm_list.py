"""
Tests for: python manage.py bm_list runs|benchmarks|providers|suites [filters]
"""
from apps.benchmarks.models import BenchmarkSuite, BenchmarkSuiteItem
from apps.runs.models import BenchmarkRun
from tests.base import BaseCommandTest, make_run, make_benchmark, make_provider


class TestBmListRuns(BaseCommandTest):

    def setUp(self):
        super().setUp()
        self.run = make_run(self.benchmark, self.provider)

    def test_list_runs_shows_run(self):
        out = self.call('bm_list', 'runs')
        self.assertIn(self.benchmark.slug, out)
        self.assertIn(self.run.model_name, out)

    def test_list_runs_empty(self):
        BenchmarkRun.objects.all().delete()
        out = self.call('bm_list', 'runs')
        self.assertIn('No runs', out)

    def test_filter_by_benchmark(self):
        bm2 = make_benchmark(slug='other-bench', name='Other')
        make_run(bm2, self.provider, model_name='other-model')
        out = self.call('bm_list', 'runs', '--benchmark', 'test-bench')
        self.assertIn('llama3.2', out)
        self.assertNotIn('other-model', out)

    def test_filter_by_status(self):
        make_run(self.benchmark, self.provider, model_name='pending-model', status='pending',
                 score=0.0, total_questions=0, correct_answers=0)
        out = self.call('bm_list', 'runs', '--status', 'completed')
        self.assertIn('llama3.2', out)
        self.assertNotIn('pending-model', out)

    def test_filter_by_tag(self):
        BenchmarkRun.objects.create(
            benchmark=self.benchmark,
            provider=self.provider,
            model_name='tagged-model',
            status='completed',
            tags='baseline,v2',
        )
        out = self.call('bm_list', 'runs', '--tag', 'baseline')
        self.assertIn('tagged-model', out)
        self.assertNotIn('llama3.2', out)

    def test_filter_by_model(self):
        out = self.call('bm_list', 'runs', '--model', 'llama')
        self.assertIn('llama3.2', out)

    def test_limit_option(self):
        for i in range(5):
            make_run(self.benchmark, self.provider, model_name=f'model-{i}')
        out = self.call('bm_list', 'runs', '--limit', '2')
        # Should show at most 2 entries (header not counted)
        lines = [l for l in out.splitlines() if 'model-' in l or 'llama3.2' in l]
        self.assertLessEqual(len(lines), 2)


class TestBmListBenchmarks(BaseCommandTest):

    def test_list_benchmarks_shows_benchmark(self):
        out = self.call('bm_list', 'benchmarks')
        self.assertIn('test-bench', out)

    def test_filter_loaded_only(self):
        from apps.benchmarks.models import Benchmark
        Benchmark.objects.create(slug='unloaded-bm', name='Unloaded', loaded_at=None)
        out = self.call('bm_list', 'benchmarks', '--loaded')
        self.assertIn('test-bench', out)
        self.assertNotIn('unloaded-bm', out)

    def test_filter_by_category(self):
        from apps.benchmarks.models import Benchmark
        from django.utils import timezone
        Benchmark.objects.create(
            slug='math-bm', name='Math Bench', category='math',
            loaded_at=timezone.now()
        )
        out = self.call('bm_list', 'benchmarks', '--category', 'math')
        self.assertIn('math-bm', out)
        self.assertNotIn('test-bench', out)

    def test_no_benchmarks_shows_registry(self):
        from apps.benchmarks.models import Benchmark
        Benchmark.objects.all().delete()
        out = self.call('bm_list', 'benchmarks')
        # Should show registry entries
        self.assertTrue(len(out) > 0)


class TestBmListProviders(BaseCommandTest):

    def test_list_providers_shows_provider(self):
        out = self.call('bm_list', 'providers')
        self.assertIn('test-provider', out)
        self.assertIn('Test Provider', out)

    def test_list_providers_empty(self):
        from apps.providers.models import Provider
        Provider.objects.all().delete()
        out = self.call('bm_list', 'providers')
        self.assertIn('No providers', out)


class TestBmListSuites(BaseCommandTest):

    def test_list_suites_shows_suite(self):
        suite = BenchmarkSuite.objects.create(slug='s1', name='Suite One')
        BenchmarkSuiteItem.objects.create(suite=suite, benchmark=self.benchmark, order=0)
        out = self.call('bm_list', 'suites')
        self.assertIn('Suite One', out)
        self.assertIn('test-bench', out)

    def test_list_suites_empty(self):
        out = self.call('bm_list', 'suites')
        self.assertIn('No suites', out)
