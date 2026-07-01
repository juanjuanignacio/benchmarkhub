from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('benchmarks', '0005_add_prompt_template'),
    ]

    operations = [
        # Benchmark: add benchmark_type field
        migrations.AddField(
            model_name='benchmark',
            name='benchmark_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('text', 'Text'),
                    ('vision', 'Vision (Image)'),
                    ('audio', 'Audio / Speech'),
                    ('agentic', 'Agentic / Tool Use'),
                ],
                default='text',
            ),
        ),
        # Benchmark: update category choices (handled by model, no migration needed)

        # BenchmarkQuestion: add image_paths (JSONField, list of relative paths)
        migrations.AddField(
            model_name='benchmarkquestion',
            name='image_paths',
            field=models.JSONField(default=list, blank=True),
        ),
        # BenchmarkQuestion: add audio_path
        migrations.AddField(
            model_name='benchmarkquestion',
            name='audio_path',
            field=models.CharField(max_length=500, blank=True, default=''),
        ),
    ]
