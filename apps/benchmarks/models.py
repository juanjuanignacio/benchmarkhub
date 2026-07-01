from django.db import models
from django.utils import timezone


class Benchmark(models.Model):
    CATEGORY_CHOICES = [
        ('reasoning', 'Reasoning'),
        ('knowledge', 'Knowledge'),
        ('math', 'Math'),
        ('coding', 'Coding'),
        ('language', 'Language'),
        ('common_sense', 'Common Sense'),
        ('clinical', 'Clinical Medicine'),
        ('biomedical', 'Biomedical Science'),
        ('vision', 'Vision & Multimodal'),
        ('audio', 'Audio & Speech'),
        ('agentic', 'Agentic / Tool Use'),
    ]

    BENCHMARK_TYPE_CHOICES = [
        ('text', 'Text'),
        ('vision', 'Vision (Image)'),
        ('audio', 'Audio / Speech'),
        ('agentic', 'Agentic / Tool Use'),
    ]

    slug = models.SlugField(unique=True, max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='knowledge')
    benchmark_type = models.CharField(max_length=20, choices=BENCHMARK_TYPE_CHOICES, default='text')
    num_questions = models.IntegerField(default=0)
    loaded_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    # Optional custom prompt template. Overrides the loader's default format_prompt.
    # Available placeholders: {question} {choice_a} {choice_b} {choice_c} {choice_d}
    prompt_template = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_loaded(self):
        return self.loaded_at is not None and self.num_questions > 0

    def get_question_count(self):
        return self.questions.count()


class BenchmarkQuestion(models.Model):
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, related_name='questions')
    question_id = models.CharField(max_length=200)
    question = models.TextField()
    choice_a = models.TextField(null=True, blank=True)
    choice_b = models.TextField(null=True, blank=True)
    choice_c = models.TextField(null=True, blank=True)
    choice_d = models.TextField(null=True, blank=True)
    correct_answer = models.CharField(max_length=500)
    subject = models.CharField(max_length=200, blank=True)
    difficulty = models.CharField(max_length=50, blank=True)
    # RAG support: stores the retrieved passage/document used as context
    context = models.TextField(blank=True, default='')
    # Multimodal support
    image_paths = models.JSONField(default=list, blank=True)
    audio_path = models.CharField(max_length=500, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['question_id']
        unique_together = ['benchmark', 'question_id']

    def __str__(self):
        return f"{self.benchmark.name} - {self.question_id}"

    def get_choices(self):
        choices = {}
        if self.choice_a:
            choices['A'] = self.choice_a
        if self.choice_b:
            choices['B'] = self.choice_b
        if self.choice_c:
            choices['C'] = self.choice_c
        if self.choice_d:
            choices['D'] = self.choice_d
        return choices


class PromptTemplate(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    content = models.TextField(
        help_text='Use {question}, {choice_a}, {choice_b}, {choice_c}, {choice_d}, {correct_answer} as placeholders'
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BenchmarkSuite(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class BenchmarkSuiteItem(models.Model):
    suite = models.ForeignKey(BenchmarkSuite, on_delete=models.CASCADE, related_name='items')
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = ['suite', 'benchmark']
