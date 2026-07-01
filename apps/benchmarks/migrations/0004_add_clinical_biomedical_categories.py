from django.db import migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('benchmarks', '0003_add_question_context'),
    ]

    operations = [
        migrations.AlterField(
            model_name='benchmark',
            name='category',
            field=django.db.models.fields.CharField(
                choices=[
                    ('reasoning', 'Reasoning'),
                    ('knowledge', 'Knowledge'),
                    ('math', 'Math'),
                    ('coding', 'Coding'),
                    ('language', 'Language'),
                    ('common_sense', 'Common Sense'),
                    ('clinical', 'Clinical Medicine'),
                    ('biomedical', 'Biomedical Science'),
                ],
                default='knowledge',
                max_length=50,
            ),
        ),
    ]
