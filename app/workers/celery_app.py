from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "naija_security",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Africa/Lagos",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        # News scraper — every hour
        "hourly-news-scrape": {
            "task": "app.workers.tasks.scrape_news",
            "schedule": crontab(minute=0),
            "kwargs": {"fetch_bodies": False},
        },
        # Incremental ACLED sync every Sunday at 02:00 WAT
        "acled-weekly-sync": {
            "task": "app.workers.tasks.sync_acled",
            "schedule": crontab(hour=2, minute=0, day_of_week="sunday"),
            "kwargs": {"full_resync": False},
        },
        # Recalculate risk scores for all LGAs every day at 03:00 WAT
        "daily-risk-score-update": {
            "task": "app.workers.tasks.update_risk_scores",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
