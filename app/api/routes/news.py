from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.news import NewsArticleOut, PaginatedNews

router = APIRouter(prefix="/news", tags=["news"])

PAGE_SIZE_MAX = 100


def _build_article(row) -> NewsArticleOut:
    return NewsArticleOut(
        id=row.id,
        headline=row.headline,
        url=row.url,
        source=row.source,
        published_at=row.published_at,
        sentiment_score=row.sentiment_score,
        sentiment_label=row.sentiment_label,
        extracted_state=row.extracted_state,
        extracted_lga=row.extracted_lga,
        extracted_entities=row.extracted_entities,
        lga_id=row.lga_id,
    )


@router.get("", response_model=PaginatedNews)
async def list_news(
    security_only: bool = Query(True, description="Only security-relevant articles"),
    state: str | None = Query(None, description="Filter by state"),
    source: str | None = Query(None, description="Filter by news source"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated news feed, newest first.
    By default returns only security-relevant articles.
    """
    conditions = []
    params: dict = {"offset": (page - 1) * page_size, "limit": page_size}

    if security_only:
        conditions.append("security_relevant = true")
    if state:
        conditions.append("extracted_state ILIKE :state")
        params["state"] = f"%{state}%"
    if source:
        conditions.append("source ILIKE :source")
        params["source"] = f"%{source}%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = text(f"SELECT COUNT(*) FROM news_articles {where}")
    total = (await db.execute(count_sql, params)).scalar() or 0

    rows_sql = text(f"""
        SELECT id, headline, url, source, published_at,
               sentiment_score, sentiment_label,
               extracted_state, extracted_lga, extracted_entities, lga_id
        FROM news_articles
        {where}
        ORDER BY published_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    rows = (await db.execute(rows_sql, params)).fetchall()

    return PaginatedNews(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_article(r) for r in rows],
    )


@router.get("/lga/{lga_id}", response_model=PaginatedNews)
async def news_for_lga(
    lga_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """Recent security news articles linked to a specific LGA."""
    params = {
        "lga_id": lga_id,
        "offset": (page - 1) * page_size,
        "limit": page_size,
    }
    total = (await db.execute(
        text("SELECT COUNT(*) FROM news_articles WHERE lga_id = :lga_id AND security_relevant = true"),
        params,
    )).scalar() or 0

    rows = (await db.execute(text("""
        SELECT id, headline, url, source, published_at,
               sentiment_score, sentiment_label,
               extracted_state, extracted_lga, extracted_entities, lga_id
        FROM news_articles
        WHERE lga_id = :lga_id AND security_relevant = true
        ORDER BY published_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)).fetchall()

    return PaginatedNews(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_article(r) for r in rows],
    )


@router.get("/state/{state}", response_model=PaginatedNews)
async def news_for_state(
    state: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """Recent security news for all LGAs in a state."""
    params = {
        "state": f"%{state}%",
        "offset": (page - 1) * page_size,
        "limit": page_size,
    }
    total = (await db.execute(text("""
        SELECT COUNT(*) FROM news_articles
        WHERE extracted_state ILIKE :state AND security_relevant = true
    """), params)).scalar() or 0

    rows = (await db.execute(text("""
        SELECT id, headline, url, source, published_at,
               sentiment_score, sentiment_label,
               extracted_state, extracted_lga, extracted_entities, lga_id
        FROM news_articles
        WHERE extracted_state ILIKE :state AND security_relevant = true
        ORDER BY published_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)).fetchall()

    return PaginatedNews(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_article(r) for r in rows],
    )
