"""
RSS-based news scraper for Nigerian security news.

Strategy:
  - Fetch RSS feeds from 10 Nigerian news sources (async httpx)
  - Parse with feedparser (sync, run in thread executor)
  - Return raw article dicts; NLP + DB writes handled by news_pipeline.py
  - Optionally fetch full article body via BeautifulSoup for sites that
    publish only summaries in their RSS
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NaijaSecurityBot/1.0; "
        "security research aggregator; +https://github.com/placeholder)"
    )
}


@dataclass
class NewsSource:
    name: str
    rss_url: str
    full_text_in_rss: bool = True   # False → fetch article page for body
    body_css_selector: str = "article"  # CSS selector for body on article page


NEWS_SOURCES: list[NewsSource] = [
    NewsSource(
        name="Punch",
        rss_url="https://rss.punchng.com/v1/category/latest_news",
        full_text_in_rss=False,
        body_css_selector="div.post-content",
    ),
    NewsSource(
        name="Vanguard",
        rss_url="https://www.vanguardngr.com/feed/",
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
    NewsSource(
        name="Premium Times",
        rss_url="https://www.premiumtimesng.com/feed",
        full_text_in_rss=True,
    ),
    NewsSource(
        name="Daily Trust",
        rss_url="https://dailytrust.com/feed",
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
    NewsSource(
        name="The Guardian Nigeria",
        rss_url="https://guardian.ng/news/feed/",  # category feed bypasses bot block
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
    NewsSource(
        name="Channels TV",
        rss_url="https://www.channelstv.com/feed/",
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
    NewsSource(
        name="HumAngle",
        rss_url="https://humangle.ng/category/security/feed/",  # security category only
        full_text_in_rss=True,
    ),
    NewsSource(
        name="SaharaReporters",
        rss_url="https://saharareporters.com/rss.xml",
        full_text_in_rss=False,
        body_css_selector="div.field-items",
    ),
    NewsSource(
        name="ThisDay",
        rss_url="https://www.thisdaylive.com/feed/",  # redirects to this anyway
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
    NewsSource(
        name="Tribune",
        rss_url="https://tribuneonlineng.com/category/news/feed/",  # category feed
        full_text_in_rss=False,
        body_css_selector="div.entry-content",
    ),
]


def _parse_rss_date(entry: Any) -> datetime | None:
    """Return timezone-aware datetime from an RSS entry."""
    # feedparser normalises to time.struct_time in entry.published_parsed
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        import calendar
        ts = calendar.timegm(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if hasattr(entry, "published") and entry.published:
        try:
            return parsedate_to_datetime(entry.published)
        except Exception:
            pass
    return None


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def _summary_from_entry(entry: Any) -> str:
    """Extract plain text summary from RSS entry."""
    raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    if "<" in raw:
        return _html_to_text(raw)
    return raw.strip()


def _full_content_from_entry(entry: Any) -> str:
    """Extract full text if RSS provides it (e.g. <content:encoded>)."""
    content_list = getattr(entry, "content", [])
    if content_list:
        raw = content_list[0].get("value", "")
        if raw:
            return _html_to_text(raw)
    return ""


def _parse_feed(raw_bytes: bytes, source_name: str) -> list[dict]:
    """Run feedparser (sync, CPU-bound) on raw RSS bytes."""
    feed = feedparser.parse(raw_bytes)
    articles = []
    for entry in feed.entries:
        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or ""
        if not url or not title:
            continue
        articles.append({
            "url": url.strip(),
            "headline": title.strip(),
            "summary": _summary_from_entry(entry),
            "full_content": _full_content_from_entry(entry),
            "published_at": _parse_rss_date(entry),
            "source": source_name,
        })
    return articles


async def _fetch_rss(client: httpx.AsyncClient, source: NewsSource) -> list[dict]:
    try:
        resp = await client.get(
            source.rss_url, headers=HEADERS, timeout=20.0, follow_redirects=True
        )
        resp.raise_for_status()
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(
            None, _parse_feed, resp.content, source.name
        )
        logger.info("[%s] fetched %d articles", source.name, len(articles))
        return articles
    except Exception as exc:
        logger.warning("[%s] RSS fetch failed: %s", source.name, type(exc).__name__ + ": " + str(exc)[:120])
        return []


async def _fetch_article_body(
    client: httpx.AsyncClient, url: str, css_selector: str
) -> str:
    """Fetch full article text from article page."""
    try:
        resp = await client.get(url, headers=HEADERS, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        container = soup.select_one(css_selector)
        if container:
            return _html_to_text(str(container))
        return _html_to_text(resp.text)
    except Exception as exc:
        logger.debug("Body fetch failed for %s: %s", url, exc)
        return ""


async def scrape_all_sources(
    fetch_bodies: bool = False,
    sources: list[NewsSource] | None = None,
) -> list[dict]:
    """
    Fetch articles from all (or given) RSS sources.

    Args:
        fetch_bodies: If True, also fetch full article text for sources
                      that don't include it in RSS. Slower but richer.
        sources: Override the default NEWS_SOURCES list.

    Returns:
        List of raw article dicts (not yet NLP-enriched or saved to DB).
    """
    targets = sources or NEWS_SOURCES

    async with httpx.AsyncClient() as client:
        rss_tasks = [_fetch_rss(client, src) for src in targets]
        results = await asyncio.gather(*rss_tasks)

        all_articles: list[dict] = []
        seen_urls: set[str] = set()

        source_map = {src.name: src for src in targets}

        for src_articles in results:
            for article in src_articles:
                url = article["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Use full content from RSS if available
                body = article["full_content"] or article["summary"]

                # Optionally fetch full body from article page
                if fetch_bodies and not article["full_content"]:
                    src = source_map.get(article["source"])
                    if src and not src.full_text_in_rss:
                        body = await _fetch_article_body(
                            client, url, src.body_css_selector
                        ) or body

                article["body"] = body
                all_articles.append(article)

    logger.info("Total unique articles scraped: %d", len(all_articles))
    return all_articles
