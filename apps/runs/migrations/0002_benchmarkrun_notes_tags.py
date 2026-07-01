from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('runs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='benchmarkrun',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='tags',
            field=models.CharField(blank=True, default='', help_text='Comma-separated tags', max_length=500),
        ),
    ]
