"""DailyPulse's background jobs: push alerts for breaking news (Chapter 39).

The worker runs from the same image as the API, with another command: celery -A tasks worker.
It finds Redis, its broker, through CELERY_BROKER_URL, and the archive through settings.py.
"""

import psycopg
from celery import Celery
from celery.utils.log import get_task_logger

from settings import archive_conninfo

app = Celery("dailypulse")  # the broker comes from CELERY_BROKER_URL
app.conf.update(
    task_acks_late=True,  # acknowledge after the job: a worker that dies gives it back (Ch 35)
    worker_prefetch_multiplier=1,  # one job at a time per process
    task_ignore_result=True,  # nobody waits for an alert's answer, so no result store
    broker_connection_retry_on_startup=True,  # a worker started before Redis waits for it
)
logger = get_task_logger(__name__)

GROUPS = ("city", "traffic", "election")  # the phone app's pretend subscriber groups


@app.task
def send_push_alert(text: str) -> int:
    """Pretend to push the banner to every group's phones, then log it in the archive."""
    with psycopg.connect(archive_conninfo()) as connection:
        connection.execute(
            "INSERT INTO push_log (text, groups) VALUES (%s, %s)", (text, len(GROUPS))
        )
    logger.info("push alert sent to %d groups: %s", len(GROUPS), text)
    return len(GROUPS)
