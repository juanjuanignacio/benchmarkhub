import threading
import time
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler_thread = None


def start_scheduler():
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, daemon=True, name='scheduler'
    )
    _scheduler_thread.start()


def _scheduler_loop():
    while True:
        try:
            _check_scheduled_runs()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(60)  # check every minute


def _check_scheduled_runs():
    from .models import ScheduledRun, BenchmarkRun
    from .runner import start_run_in_background
    from datetime import timedelta

    now = timezone.now()
    due = ScheduledRun.objects.filter(is_active=True, run_at__lte=now)
    for scheduled in due:
        try:
            run = BenchmarkRun.objects.create(
                benchmark=scheduled.benchmark,
                provider=scheduled.provider,
                model_name=scheduled.model_name,
                num_questions=scheduled.num_questions,
                system_prompt=scheduled.system_prompt,
                temperature=scheduled.temperature,
                max_tokens=scheduled.max_tokens,
            )
            start_run_in_background(run.id)
            scheduled.last_run_at = now
            scheduled.last_run = run
            if scheduled.frequency == 'once':
                scheduled.is_active = False
            elif scheduled.frequency == 'daily':
                scheduled.run_at = now + timedelta(days=1)
            elif scheduled.frequency == 'weekly':
                scheduled.run_at = now + timedelta(weeks=1)
            scheduled.save()
            logger.info(f"Scheduled run '{scheduled.name}' started as run #{run.id}")
        except Exception as e:
            logger.error(f"Error starting scheduled run '{scheduled.name}': {e}")
