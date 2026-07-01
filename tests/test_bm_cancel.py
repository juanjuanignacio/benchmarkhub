"""
Tests for: python manage.py bm_cancel <run_id> [--delete]
"""
from unittest.mock import patch

from apps.runs.models import BenchmarkRun
from tests.base import BaseCommandTest, make_run


MOCK_CANCEL = 'apps.runs.management.commands.bm_cancel.cancel_run'


class TestBmCancel(BaseCommandTest):

    def test_cancel_running_run(self):
        run = make_run(self.benchmark, self.provider, status='running',
                       score=0, total_questions=10, correct_answers=0)
        with patch(MOCK_CANCEL) as mock_cancel:
            out = self.call('bm_cancel', str(run.id))
        mock_cancel.assert_called_once_with(run.id)
        self.assertIn('cancelled', out.lower())

    def test_cancel_pending_run(self):
        run = make_run(self.benchmark, self.provider, status='pending',
                       score=0, total_questions=0, correct_answers=0)
        with patch(MOCK_CANCEL):
            out = self.call('bm_cancel', str(run.id))
        self.assertIn('cancelled', out.lower())

    def test_cancel_already_completed_warns(self):
        run = make_run(self.benchmark, self.provider, status='completed')
        with patch(MOCK_CANCEL) as mock_cancel:
            out = self.call('bm_cancel', str(run.id))
        mock_cancel.assert_not_called()
        self.assertIn('already', out.lower())

    def test_cancel_and_delete(self):
        run = make_run(self.benchmark, self.provider, status='running',
                       score=0, total_questions=10, correct_answers=0)
        run_id = run.id
        with patch(MOCK_CANCEL):
            out = self.call('bm_cancel', str(run_id), '--delete')
        self.assertFalse(BenchmarkRun.objects.filter(id=run_id).exists())
        self.assertIn('deleted', out.lower())

    def test_delete_completed_run(self):
        run = make_run(self.benchmark, self.provider, status='completed')
        run_id = run.id
        with patch(MOCK_CANCEL) as mock_cancel:
            out = self.call('bm_cancel', str(run_id), '--delete')
        mock_cancel.assert_not_called()
        self.assertFalse(BenchmarkRun.objects.filter(id=run_id).exists())
        self.assertIn('deleted', out.lower())

    def test_cancel_nonexistent_run_shows_error(self):
        with patch(MOCK_CANCEL):
            out = self.call('bm_cancel', '99999')
        self.assertIn('not found', out.lower())

    def test_cancel_multiple_runs(self):
        run1 = make_run(self.benchmark, self.provider, status='running',
                        score=0, total_questions=5, correct_answers=0)
        run2 = make_run(self.benchmark, self.provider, model_name='gpt-4o',
                        status='running', score=0, total_questions=5, correct_answers=0)
        with patch(MOCK_CANCEL) as mock_cancel:
            self.call('bm_cancel', str(run1.id), str(run2.id))
        self.assertEqual(mock_cancel.call_count, 2)
