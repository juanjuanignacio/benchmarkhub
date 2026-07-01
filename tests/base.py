"""
Shared fixtures and helpers for management command tests.
"""
import io
from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone

from apps.benchmarks.models import Benchmark, BenchmarkQuestion, PromptTemplate, BenchmarkSuite, BenchmarkSuiteItem
from apps.providers.models import Provider
from apps.runs.models import BenchmarkRun, RunResult, BenchmarkSuiteRun


def make_provider(slug='test-provider', name='Test Provider', provider_type='ollama'):
    return Provider.objects.create(
        slug=slug,
        name=name,
        provider_type=provider_type,
        base_url='http://localhost:11434',
        is_active=True,
    )


def make_benchmark(slug='test-bench', name='Test Benchmark', loaded=True, num_questions=3):
    bm = Benchmark.objects.create(
        slug=slug,
        name=name,
        category='knowledge',
        num_questions=num_questions,
        loaded_at=timezone.now() if loaded else None,
    )
    for i in range(num_questions):
        BenchmarkQuestion.objects.create(
            benchmark=bm,
            question_id=str(i + 1),
            question=f'Question {i + 1}?',
            correct_answer='A',
            choice_a='Option A',
            choice_b='Option B',
            subject='general',
        )
    return bm


def make_run(benchmark, provider, model_name='llama3.2', status='completed',
             score=75.0, total_questions=10, correct_answers=7):
    return BenchmarkRun.objects.create(
        benchmark=benchmark,
        provider=provider,
        model_name=model_name,
        status=status,
        score=score,
        total_questions=total_questions,
        correct_answers=correct_answers,
        started_at=timezone.now(),
        completed_at=timezone.now() if status == 'completed' else None,
    )


def call_cmd(name, *args, **kwargs):
    """Call a management command and return stdout as a string."""
    out = io.StringIO()
    call_command(name, *args, stdout=out, **kwargs)
    return out.getvalue()


class BaseCommandTest(TestCase):
    """Base class providing common fixtures."""

    def setUp(self):
        self.provider = make_provider()
        self.benchmark = make_benchmark()

    def call(self, name, *args, **kwargs):
        return call_cmd(name, *args, **kwargs)
