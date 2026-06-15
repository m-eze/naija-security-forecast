"""
News pipeline orchestrator.

Flow:
  1. Scrape RSS feeds → raw articles
  2. Load LGA name list from DB (for location extraction)
  3. Run NLP pipeline on each article
  4. Resolve extracted LGA text → lga_id (via LGAMatcher)
  5. Bulk upsert into news_articles (conflict on URL)
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lga import LGA
from app.models.news_article import NewsArticle
from app.services.lga_matcher import LGAMatcher
from app.services.nlp import process_article
from app.services.rss_scraper import scrape_all_sources, NewsSource

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def _load_lga_names(db: AsyncSession) -> list[str]:
    result = await db.execute(select(LGA.name))
    return [row[0] for row in result.all()]


async def _upsert_batch(db: AsyncSession, records: list[dict]) -> int:
    if not records:
        return 0
    stmt = (
        insert(NewsArticle)
        .values(records)
        .on_conflict_do_update(
            index_elements=["url"],
            set_={
                "security_relevant": insert(NewsArticle).excluded.security_relevant,
                "sentiment_score": insert(NewsArticle).excluded.sentiment_score,
                "sentiment_label": insert(NewsArticle).excluded.sentiment_label,
                "extracted_state": insert(NewsArticle).excluded.extracted_state,
                "extracted_lga": insert(NewsArticle).excluded.extracted_lga,
                "extracted_entities": insert(NewsArticle).excluded.extracted_entities,
                "scrape_status": insert(NewsArticle).excluded.scrape_status,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
    return len(records)


async def run_news_pipeline(
    db: AsyncSession,
    fetch_bodies: bool = False,
    sources: list[NewsSource] | None = None,
) -> dict:
    """
    Main entry point.

    Args:
        db: async DB session
        fetch_bodies: fetch full article text (slower)
        sources: override default news sources

    Returns:
        Summary dict.
    """
    started_at = datetime.now(timezone.utc)

    # 1. Scrape RSS
    raw_articles = await scrape_all_sources(fetch_bodies=fetch_bodies, sources=sources)
    logger.info("Scraped %d raw articles", len(raw_articles))

    # 2. Load LGA names for location extraction
    lga_names = await _load_lga_names(db)

    # 3. Load LGAMatcher for ID resolution
    matcher = LGAMatcher()
    await matcher.load(db)

    total_processed = 0
    total_security = 0
    total_failed = 0
    batch: list[dict] = []

    for raw in raw_articles:
        try:
            nlp = process_article(
                headline=raw.get("headline", ""),
                body=raw.get("body", ""),
                lga_names=lga_names,
            )

            # Resolve LGA text mention → lga_id
            lga_id: uuid.UUID | None = None
            if nlp.extracted_lga or nlp.extracted_state:
                lga_id = await matcher.resolve(
                    admin2=nlp.extracted_lga,
                    admin1=nlp.extracted_state,
                    db=db,
                )

            record = {
                "lga_id": lga_id,
                "headline": raw["headline"][:500],
                "body": (raw.get("body") or "")[:50_000] or None,
                "url": raw["url"][:1000],
                "source": raw["source"],
                "published_at": raw.get("published_at"),
                "extracted_state": nlp.extracted_state,
                "extracted_lga": nlp.extracted_lga,
                "security_relevant": nlp.security_relevant,
                "sentiment_score": nlp.sentiment_score,
                "sentiment_label": nlp.sentiment_label,
                "extracted_entities": nlp.extracted_entities or None,
                "scrape_status": "processed",
            }
            batch.append(record)
            total_processed += 1
            if nlp.security_relevant:
                total_security += 1

        except Exception as exc:
            logger.error("Failed to process article '%s': %s", raw.get("url"), exc)
            total_failed += 1
            continue

        if len(batch) >= BATCH_SIZE:
            await _upsert_batch(db, batch)
            batch = []

    if batch:
        await _upsert_batch(db, batch)

    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "scraped": len(raw_articles),
        "processed": total_processed,
        "security_relevant": total_security,
        "failed": total_failed,
        "duration_seconds": round(duration, 1),
    }
    logger.info("News pipeline complete: %s", summary)
    return summary
