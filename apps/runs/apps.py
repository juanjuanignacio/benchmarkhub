from django.apps import AppConfig


class RunsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.runs'
    verbose_name = 'Benchmark Runs'

    def ready(self):
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception:
            pass
