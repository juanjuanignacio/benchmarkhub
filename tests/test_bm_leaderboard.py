"""
Tests for: python manage.py bm_leaderboard [--benchmark slug] [--limit N]
"""
from tests.base import BaseCommandTest, make_run, make_benchmark


class TestBmLeaderboard(BaseCommandTest):

    def test_no_completed_runs_shows_empty(self):
        out = self.call('bm_leaderboard')
        self.assertIn('No completed runs', out)

    def test_shows_completed_run(self):
        make_run(self.benchmark, self.provider, model_name='llama3.2', score=80.0)
        out = self.call('bm_leaderboard')
        self.assertIn('llama3.2', out)
        self.assertIn('80.0', out)

    def test_filter_by_benchmark(self):
        bm2 = make_benchmark(slug='other-bm', name='Other Bench')
        make_run(self.benchmark, self.provider, model_name='model-a', score=90.0)
        make_run(bm2, self.provider, model_name='model-b', score=60.0)
        out = self.call('bm_leaderboard', '--benchmark', 'test-bench')
        self.assertIn('model-a', out)
        self.assertNotIn('model-b', out)

    def test_shows_best_score_per_model(self):
        """If a model has multiple runs, only the best score should appear."""
        make_run(self.benchmark, self.provider, model_name='llama3.2', score=60.0)
        make_run(self.benchmark, self.provider, model_name='llama3.2', score=85.0)
        out = self.call('bm_leaderboard')
        self.assertIn('85.0', out)
        # 60.0 should not appear (it's not the best for this model+benchmark combo)
        self.assertNotIn('60.0', out)

    def test_sorted_by_score_descending(self):
        make_run(self.benchmark, self.provider, model_name='model-low', score=40.0)
        make_run(self.benchmark, self.provider, model_name='model-high', score=95.0)
        out = self.call('bm_leaderboard')
        idx_high = out.index('model-high')
        idx_low = out.index('model-low')
        self.assertLess(idx_high, idx_low)

    def test_limit_option(self):
        for i in range(5):
            make_run(self.benchmark, self.provider,
                     model_name=f'model-{i}', score=float(50 + i))
        out = self.call('bm_leaderboard', '--limit', '2')
        model_lines = [l for l in out.splitlines() if 'model-' in l]
        self.assertLessEqual(len(model_lines), 2)

    def test_shows_rank(self):
        make_run(self.benchmark, self.provider, model_name='llama3.2', score=75.0)
        out = self.call('bm_leaderboard')
        self.assertIn('1', out)

    def test_ignores_non_completed_runs(self):
        make_run(self.benchmark, self.provider, model_name='pending-model',
                 status='pending', score=0.0, total_questions=0, correct_answers=0)
        out = self.call('bm_leaderboard')
        self.assertIn('No completed runs', out)
