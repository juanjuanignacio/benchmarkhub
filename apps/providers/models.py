from django.db import models
from django.utils.text import slugify


class Provider(models.Model):
    PROVIDER_TYPE_CHOICES = [
        ('ollama', 'Ollama'),
        ('vllm', 'vLLM'),
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic'),
        ('cohere', 'Cohere'),
        ('mistral', 'Mistral'),
        ('gemini', 'Google Gemini'),
        ('groq', 'Groq'),
        ('together', 'Together AI'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=200)
    provider_type = models.CharField(max_length=50, choices=PROVIDER_TYPE_CHOICES)
    base_url = models.CharField(max_length=500, blank=True, help_text='Base URL for local providers')
    api_key = models.CharField(max_length=500, blank=True, help_text='API key (stored plain, use env vars in production)')
    default_model = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    extra_params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.provider_type})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_backend(self):
        from .backends import get_backend
        return get_backend(self)


class ProviderTest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='tests')
    model_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    response_time = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    tested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tested_at']

    def __str__(self):
        return f"{self.provider.name} test - {self.status} at {self.tested_at}"
