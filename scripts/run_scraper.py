"""
Run the news scraper pipeline manually.

Usage:
    python scripts/run_scraper.py                    # RSS only (fast)
    python scripts/run_scraper.py --fetch-bodies     # also fetch full article text
    python scripts/run_scraper.py --source Punch     # single source
    python scripts/run_scraper.py --dry-run          # scrape + NLP, no DB writes
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from app.core.database import AsyncSessionLocal
from app.services.rss_scraper import scrape_all_sources, NEWS_SOURCES
from app.services.nlp import process_article
from app.services.news_pipeline import run_news_pipeline


async def dry_run(source_name: str | None, fetch_bodies: bool) -> None:
    sources = NEWS_SOURCES
    if source_name:
        sources = [s for s in NEWS_SOURCES if s.name.lower() == source_name.lower()]
        if not sources:
            logger.error("Unknown source '%s'. Available: %s", source_name, [s.name for s in NEWS_SOURCES])
            sys.exit(1)

    articles = await scrape_all_sources(fetch_bodies=fetch_bodies, sources=sources)

    print(f"\n=== Dry run: {len(articles)} articles scraped ===\n")
    security_count = 0
    for art in articles:
        nlp = process_article(art.get("headline", ""), art.get("body", ""))
        flag = "🔴" if nlp.security_relevant else "⚪"
        print(f"{flag} [{art['source']}] {art['headline'][:90]}")
        if nlp.security_relevant:
            security_count += 1
            print(f"   sentiment={nlp.sentiment_score:+.2f} | state={nlp.extracted_state} | lga={nlp.extracted_lga}")
            if nlp.extracted_entities.get("armed_groups"):
                print(f"   groups={nlp.extracted_entities['armed_groups']}")

    print(f"\nTotal: {len(articles)} | Security-relevant: {security_count}")


async def full_run(source_name: str | None, fetch_bodies: bool) -> None:
    sources = NEWS_SOURCES
    if source_name:
        sources = [s for s in NEWS_SOURCES if s.name.lower() == source_name.lower()]
        if not sources:
            logger.error("Unknown source '%s'", source_name)
            sys.exit(1)

    async with AsyncSessionLocal() as db:
        summary = await run_news_pipeline(db, fetch_bodies=fetch_bodies, sources=sources)

    print("\n=== News Pipeline Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-bodies", action="store_true")
    parser.add_argument("--source", help="Run only this source (e.g. 'Punch')")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    args = parser.parse_args()

    if args.dry_run:
        asyncio.run(dry_run(args.source, args.fetch_bodies))
    else:
        asyncio.run(full_run(args.source, args.fetch_bodies))
