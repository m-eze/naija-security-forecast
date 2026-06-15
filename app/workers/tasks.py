import asyncio
import logging

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.services.acled_sync import run_acled_sync
from app.services.news_pipeline import run_news_pipeline
from app.services.scorer import calculate_all_scores

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.run(coro)


@celery_app.task(
    name="app.workers.tasks.sync_acled",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 min between retries
)
def sync_acled(self, full_resync: bool = False) -> dict:
    """Fetch latest Nigeria incidents from ACLED and upsert into DB."""
    logger.info("Starting ACLED sync task (full_resync=%s)", full_resync)
    try:
        async def _inner():
            async with AsyncSessionLocal() as db:
                return await run_acled_sync(db, full_resync=full_resync)

        return _run_async(_inner())
    except Exception as exc:
        logger.error("ACLED sync failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.scrape_news",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def scrape_news(self, fetch_bodies: bool = False) -> dict:
    """Fetch RSS feeds from Nigerian news sources, run NLP, upsert articles."""
    logger.info("Starting news scraper task (fetch_bodies=%s)", fetch_bodies)
    try:
        async def _inner():
            async with AsyncSessionLocal() as db:
                return await run_news_pipeline(db, fetch_bodies=fetch_bodies)

        return _run_async(_inner())
    except Exception as exc:
        logger.error("News scraper failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.update_risk_scores",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def update_risk_scores(self) -> dict:
    """Recalculate risk scores for all 775 LGAs and upsert into risk_scores."""
    logger.info("Starting risk score update task")
    try:
        async def _inner():
            async with AsyncSessionLocal() as db:
                return await calculate_all_scores(db)

        return _run_async(_inner())
    except Exception as exc:
        logger.error("Risk score update failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
