"""
Tests for: python manage.py bm_sweep <benchmark> <provider> <model>
           --temp-range MIN MAX STEP | --prompt-ids IDs | --prompt-texts TEXTS
"""
from unittest.mock import patch

from django.core.management.base import CommandError

from apps.benchmarks.models import PromptTemplate
from apps.runs.models import BenchmarkRun
from tests.base import BaseCommandTest


MOCK_RUNNER = 'apps.runs.management.commands.bm_sweep.start_run_in_background'


class TestBmSweepTemp(BaseCommandTest):

    def test_temp_sweep_creates_correct_number_of_runs(self):
        # 0.0, 0.5, 1.0 → 3 runs
        with patch(MOCK_RUNNER):
            out = self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                            '--temp-range', '0.0', '1.0', '0.5')
        runs = BenchmarkRun.objects.all()
        self.assertEqual(runs.count(), 3)

    def test_temp_sweep_stores_temperatures(self):
        with patch(MOCK_RUNNER):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                      '--temp-range', '0.0', '0.4', '0.2')
        temps = sorted(BenchmarkRun.objects.values_list('temperature', flat=True))
        self.assertEqual(len(temps), 3)
        self.assertAlmostEqual(temps[0], 0.0, places=3)
        self.assertAlmostEqual(temps[1], 0.2, places=3)
        self.assertAlmostEqual(temps[2], 0.4, places=3)

    def test_sweep_tag_applied(self):
        with patch(MOCK_RUNNER):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                      '--temp-range', '0.0', '0.0', '0.5')
        run = BenchmarkRun.objects.get()
        self.assertIn('sweep_', run.tags)

    def test_no_sweep_type_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2')

    def test_benchmark_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_sweep', 'no-bench', 'test-provider', 'llama3.2',
                      '--temp-range', '0.0', '0.5', '0.5')

    def test_provider_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_sweep', 'test-bench', 'ghost-provider', 'llama3.2',
                      '--temp-range', '0.0', '0.5', '0.5')


class TestBmSweepPrompt(BaseCommandTest):

    def test_prompt_texts_sweep_creates_runs(self):
        with patch(MOCK_RUNNER):
            out = self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                            '--prompt-texts', 'Be brief.', 'Think step by step.')
        runs = BenchmarkRun.objects.all()
        self.assertEqual(runs.count(), 2)

    def test_prompt_texts_stored_as_system_prompt(self):
        with patch(MOCK_RUNNER):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                      '--prompt-texts', 'My custom prompt.')
        run = BenchmarkRun.objects.get()
        self.assertEqual(run.system_prompt, 'My custom prompt.')

    def test_prompt_ids_sweep(self):
        pt1 = PromptTemplate.objects.create(name='P1', content='Be concise.')
        pt2 = PromptTemplate.objects.create(name='P2', content='Be verbose.')
        with patch(MOCK_RUNNER):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                      '--prompt-ids', str(pt1.id), str(pt2.id))
        runs = BenchmarkRun.objects.all()
        self.assertEqual(runs.count(), 2)
        prompts = set(runs.values_list('system_prompt', flat=True))
        self.assertIn('Be concise.', prompts)
        self.assertIn('Be verbose.', prompts)

    def test_prompt_id_not_found_raises(self):
        with self.assertRaises(CommandError):
            self.call('bm_sweep', 'test-bench', 'test-provider', 'llama3.2',
                      '--prompt-ids', '99999')

    def test_list_prompts_shows_empty(self):
        out = self.call('bm_sweep', '--list-prompts')
        self.assertIn('No saved prompts', out)

    def test_list_prompts_shows_prompts(self):
        PromptTemplate.objects.create(name='My Prompt', content='Answer in one word.')
        out = self.call('bm_sweep', '--list-prompts')
        self.assertIn('My Prompt', out)
