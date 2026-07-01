from django.db import models
from django.utils import timezone


class BenchmarkSuiteRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    suite = models.ForeignKey(
        'benchmarks.BenchmarkSuite', on_delete=models.CASCADE, related_name='suite_runs'
    )
    provider = models.ForeignKey(
        'providers.Provider', on_delete=models.CASCADE
    )
    model_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    num_questions_per_benchmark = models.IntegerField(default=0)
    temperature = models.FloatField(default=0.0)
    max_tokens = models.IntegerField(default=512)
    system_prompt = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.suite.name} / {self.model_name}"

    @property
    def total_score(self):
        runs = self.benchmark_runs.filter(status='completed')
        if runs.exists():
            return runs.aggregate(avg=models.Avg('score'))['avg'] or 0.0
        return 0.0

    @property
    def progress(self):
        total = self.suite.items.count()
        done = self.benchmark_runs.filter(status__in=['completed', 'failed', 'cancelled']).count()
        return (done, total)


class BenchmarkRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    benchmark = models.ForeignKey(
        'benchmarks.Benchmark', on_delete=models.CASCADE, related_name='runs'
    )
    provider = models.ForeignKey(
        'providers.Provider', on_delete=models.CASCADE, related_name='runs'
    )
    model_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    num_questions = models.IntegerField(
        default=0, help_text='Number of questions to run (0 = all)'
    )
    system_prompt = models.TextField(blank=True)
    temperature = models.FloatField(default=0.0)
    max_tokens = models.IntegerField(default=512)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    total_questions = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    score = models.FloatField(default=0.0, help_text='Score as percentage 0-100')

    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    thread_id = models.CharField(max_length=100, blank=True, help_text='Thread identifier for cancellation')
    notes = models.TextField(blank=True, default='')
    tags = models.CharField(max_length=500, blank=True, default='', help_text='Comma-separated tags')

    # New fields
    suite_run = models.ForeignKey(
        'BenchmarkSuiteRun', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='benchmark_runs'
    )
    parallel_workers = models.IntegerField(default=1)
    few_shot_count = models.IntegerField(default=0)
    use_cot = models.BooleanField(default=False)
    webhook_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.benchmark.name} / {self.model_name} [{self.status}]"

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (timezone.now() - self.started_at).total_seconds()
        return None

    @property
    def progress_pct(self):
        if self.total_questions > 0:
            answered = self.results.count()
            return min(100, int(answered / self.total_questions * 100))
        return 0

    def compute_score(self):
        total = self.results.count()
        correct = self.results.filter(is_correct=True).count()
        if total > 0:
            self.score = correct / total * 100
            self.correct_answers = correct
            self.total_questions = total
        return self.score


class RunResult(models.Model):
    run = models.ForeignKey(BenchmarkRun, on_delete=models.CASCADE, related_name='results')
    question = models.ForeignKey(
        'benchmarks.BenchmarkQuestion', on_delete=models.CASCADE, related_name='results'
    )
    model_response = models.TextField()
    parsed_answer = models.CharField(max_length=100)
    is_correct = models.BooleanField(null=True, blank=True)
    response_time = models.FloatField(default=0.0, help_text='Response time in seconds')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Token tracking
    tokens_input = models.IntegerField(default=0)
    tokens_output = models.IntegerField(default=0)
    estimated_cost = models.FloatField(default=0.0)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        status = 'correct' if self.is_correct else 'incorrect'
        return f"Result for {self.run} - Q{self.question.question_id} ({status})"


class ScheduledRun(models.Model):
    FREQUENCY_CHOICES = [
        ('once', 'Once'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
    ]
    name = models.CharField(max_length=200)
    benchmark = models.ForeignKey('benchmarks.Benchmark', on_delete=models.CASCADE)
    provider = models.ForeignKey('providers.Provider', on_delete=models.CASCADE)
    model_name = models.CharField(max_length=200)
    num_questions = models.IntegerField(default=0)
    system_prompt = models.TextField(blank=True)
    temperature = models.FloatField(default=0.0)
    max_tokens = models.IntegerField(default=512)
    run_at = models.DateTimeField(help_text='When to run next')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='once')
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run = models.ForeignKey(
        'BenchmarkRun', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='scheduled_runs'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['run_at']

    def __str__(self):
        return self.name


class RunTemplate(models.Model):
    """
    Saved run configuration that can be applied when creating a new run.
    Stores all execution parameters so users don't have to re-enter them
    every time they benchmark with the same setup.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=300, blank=True)
    model_name = models.CharField(max_length=200)
    temperature = models.FloatField(default=0.0)
    max_tokens = models.IntegerField(default=512)
    system_prompt = models.TextField(blank=True)
    num_questions = models.IntegerField(
        default=0, help_text='0 = use all benchmark questions'
    )
    parallel_workers = models.IntegerField(default=1)
    few_shot_count = models.IntegerField(default=0)
    use_cot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def as_dict(self):
        """Return parameters as a plain dict for form pre-fill."""
        return {
            'model_name': self.model_name,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'system_prompt': self.system_prompt,
            'num_questions': self.num_questions if self.num_questions else '',
            'parallel_workers': self.parallel_workers,
            'few_shot_count': self.few_shot_count,
            'use_cot': self.use_cot,
        }
