from datetime import datetime, timedelta, timezone
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


# Approximate state centroids (lat, lng) used when no LGA centroid is available
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Abia": (5.4527, 7.5248),
    "Adamawa": (9.3265, 12.3984),
    "Akwa Ibom": (4.9057, 7.8537),
    "Anambra": (6.2104, 7.0739),
    "Bauchi": (10.3103, 9.8442),
    "Bayelsa": (4.7719, 6.0699),
    "Benue": (7.3369, 8.7400),
    "Borno": (11.8333, 13.1500),
    "Cross River": (5.8702, 8.5988),
    "Delta": (5.8904, 5.6804),
    "Ebonyi": (6.2649, 8.0137),
    "Edo": (6.3350, 5.6037),
    "Ekiti": (7.7190, 5.3110),
    "Enugu": (6.4584, 7.5464),
    "Gombe": (10.2791, 11.1670),
    "Imo": (5.4920, 7.0263),
    "Jigawa": (12.2280, 9.5616),
    "Kaduna": (10.5222, 7.4383),
    "Kano": (12.0022, 8.5920),
    "Katsina": (12.9816, 7.6163),
    "Kebbi": (11.4942, 4.2333),
    "Kogi": (7.8000, 6.7400),
    "Kwara": (8.9669, 4.3874),
    "Lagos": (6.5244, 3.3792),
    "Nasarawa": (8.5378, 8.3222),
    "Niger": (9.9309, 5.5983),
    "Ogun": (7.1607, 3.3488),
    "Ondo": (7.2500, 5.2000),
    "Osun": (7.5629, 4.5200),
    "Oyo": (8.1574, 3.6141),
    "Plateau": (9.2182, 9.5170),
    "Rivers": (4.7799, 6.9990),
    "Sokoto": (13.0059, 5.2476),
    "Taraba": (7.9994, 10.7744),
    "Yobe": (12.2941, 11.4390),
    "Zamfara": (12.1702, 6.6577),
    "FCT": (9.0579, 7.4951),
    "Abuja": (9.0579, 7.4951),
}


@router.get("/pins")
async def get_news_pins(
    days: int = Query(7, ge=1, le=30, description="Days of history to include"),
    db: AsyncSession = Depends(get_db),
):
    """
    Geolocated security news for the map pin overlay.
    Uses LGA centroid when available, falls back to state centroid.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (await db.execute(text("""
        SELECT
            n.id,
            n.headline,
            n.url,
            n.source,
            n.published_at,
            n.sentiment_label,
            n.extracted_state,
            n.extracted_lga,
            l.name           AS lga_name,
            ST_Y(l.centroid) AS lat,
            ST_X(l.centroid) AS lng
        FROM news_articles n
        LEFT JOIN lgas l ON l.id = n.lga_id
        WHERE n.security_relevant = true
          AND n.published_at >= :cutoff
          AND (n.lga_id IS NOT NULL OR n.extracted_state IS NOT NULL)
        ORDER BY n.published_at DESC
        LIMIT 300
    """), {"cutoff": cutoff})).fetchall()

    pins = []
    for row in rows:
        lat, lng = row.lat, row.lng
        if lat is None or lng is None:
            coords = _STATE_CENTROIDS.get(row.extracted_state or "")
            if not coords:
                continue
            lat, lng = coords

        pins.append({
            "id": str(row.id),
            "headline": row.headline,
            "url": row.url,
            "source": row.source,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "sentiment_label": row.sentiment_label or "neutral",
            "state": row.extracted_state,
            "lga": row.lga_name or row.extracted_lga,
            "lat": round(float(lat), 5),
            "lng": round(float(lng), 5),
        })

    return {"pins": pins, "count": len(pins)}
