from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('benchmarks', '0002_prompttemplate_benchmarksuite_benchmarksuiteitem'),
        ('providers', '0001_initial'),
        ('runs', '0002_benchmarkrun_notes_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='BenchmarkSuiteRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('model_name', models.CharField(max_length=200)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')],
                    default='pending', max_length=20
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('num_questions_per_benchmark', models.IntegerField(default=0)),
                ('temperature', models.FloatField(default=0.0)),
                ('max_tokens', models.IntegerField(default=512)),
                ('system_prompt', models.TextField(blank=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='providers.provider')),
                ('suite', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suite_runs', to='benchmarks.benchmarksuite')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='suite_run',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='benchmark_runs', to='runs.benchmarksuiterun'
            ),
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='parallel_workers',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='few_shot_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='use_cot',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='webhook_url',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='runresult',
            name='tokens_input',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='runresult',
            name='tokens_output',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='runresult',
            name='estimated_cost',
            field=models.FloatField(default=0.0),
        ),
        migrations.CreateModel(
            name='ScheduledRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('model_name', models.CharField(max_length=200)),
                ('num_questions', models.IntegerField(default=0)),
                ('system_prompt', models.TextField(blank=True)),
                ('temperature', models.FloatField(default=0.0)),
                ('max_tokens', models.IntegerField(default=512)),
                ('run_at', models.DateTimeField(help_text='When to run next')),
                ('frequency', models.CharField(
                    choices=[('once', 'Once'), ('daily', 'Daily'), ('weekly', 'Weekly')],
                    default='once', max_length=20
                )),
                ('is_active', models.BooleanField(default=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('benchmark', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='benchmarks.benchmark')),
                ('last_run', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='scheduled_runs', to='runs.benchmarkrun'
                )),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='providers.provider')),
            ],
            options={
                'ordering': ['run_at'],
            },
        ),
    ]
