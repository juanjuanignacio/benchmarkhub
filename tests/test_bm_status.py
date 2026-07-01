"""
Tests for: python manage.py bm_status <run_id> [--watch]
"""
from tests.base import BaseCommandTest, make_run


class TestBmStatus(BaseCommandTest):

    def setUp(self):
        super().setUp()
        self.run = make_run(self.benchmark, self.provider)

    def test_shows_run_info(self):
        out = self.call('bm_status', str(self.run.id))
        self.assertIn(str(self.run.id), out)
        self.assertIn(self.benchmark.name, out)
        self.assertIn(self.run.model_name, out)

    def test_shows_status(self):
        out = self.call('bm_status', str(self.run.id))
        self.assertIn('COMPLETED', out.upper())

    def test_shows_score_for_completed(self):
        out = self.call('bm_status', str(self.run.id))
        self.assertIn('75.0', out)

    def test_run_not_found(self):
        # Should print error but not raise
        out = self.call('bm_status', '99999')
        self.assertIn('not found', out.lower())

    def test_multiple_run_ids(self):
        run2 = make_run(self.benchmark, self.provider, model_name='gpt-4o')
        out = self.call('bm_status', str(self.run.id), str(run2.id))
        self.assertIn('llama3.2', out)
        self.assertIn('gpt-4o', out)

    def test_pending_run_no_score(self):
        from apps.runs.models import BenchmarkRun
        pending = make_run(self.benchmark, self.provider, status='pending',
                           score=0.0, total_questions=0, correct_answers=0)
        out = self.call('bm_status', str(pending.id))
        self.assertIn('PENDING', out.upper())

    def test_failed_run_shows_status(self):
        from apps.runs.models import BenchmarkRun
        from django.utils import timezone
        failed = BenchmarkRun.objects.create(
            benchmark=self.benchmark,
            provider=self.provider,
            model_name='bad-model',
            status='failed',
            error_message='Connection timeout',
        )
        out = self.call('bm_status', str(failed.id))
        self.assertIn('FAILED', out.upper())
        self.assertIn('Connection timeout', out)

    def test_shows_tags_when_present(self):
        from apps.runs.models import BenchmarkRun
        tagged = BenchmarkRun.objects.create(
            benchmark=self.benchmark,
            provider=self.provider,
            model_name='tagged-model',
            status='completed',
            tags='baseline,v1',
        )
        out = self.call('bm_status', str(tagged.id))
        self.assertIn('baseline', out)
