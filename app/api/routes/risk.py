import json
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.risk import (
    GeoFeature,
    GeoFeatureProperties,
    GeoJSONResponse,
    LGAMapPoint,
    MapResponse,
    NationalSummary,
    RiskScoreDetail,
    StateRiskSummary,
)

router = APIRouter(prefix="/risk", tags=["risk"])


def _today_str() -> str:
    return date.today().isoformat()


# ── Map endpoint (lightweight — centroids only, no geometry) ────────────────

@router.get("/map", response_model=MapResponse)
async def get_map_scores(db: AsyncSession = Depends(get_db)):
    """
    All 775 LGAs with centroid coordinates and current risk score.
    Designed for the frontend map layer — no heavy geometry included.
    """
    sql = text("""
        SELECT
            l.id,
            l.name,
            l.state,
            ST_X(l.centroid)  AS lng,
            ST_Y(l.centroid)  AS lat,
            r.score,
            r.level
        FROM lgas l
        LEFT JOIN risk_scores r
            ON r.lga_id = l.id
            AND r.score_date = CURRENT_DATE
            AND r.is_forecast = false
        ORDER BY l.state, l.name
    """)
    rows = (await db.execute(sql)).fetchall()

    lgas = [
        LGAMapPoint(
            id=row.id,
            name=row.name,
            state=row.state,
            lng=round(row.lng, 5) if row.lng else None,
            lat=round(row.lat, 5) if row.lat else None,
            score=row.score,
            level=row.level,
        )
        for row in rows
    ]

    return MapResponse(
        score_date=date.today(),
        lgas=lgas,
        total=len(lgas),
    )


# ── GeoJSON endpoint (polygon boundaries + scores for choropleth) ───────────

@router.get("/geojson")
async def get_geojson(
    state: str | None = Query(None, description="Filter by state name"),
    simplified: bool = Query(True, description="Simplify geometry (faster)"),
    score_date: date | None = Query(None, description="Date for scores (YYYY-MM-DD). Defaults to today. Future dates return forecast scores."),
    db: AsyncSession = Depends(get_db),
):
    """
    GeoJSON FeatureCollection of LGA boundaries with risk scores.
    Pass ?score_date=YYYY-MM-DD to get forecast scores for future dates.
    """
    geom_expr = (
        "ST_AsGeoJSON(ST_SimplifyPreserveTopology(l.geometry, 0.01))"
        if simplified
        else "ST_AsGeoJSON(l.geometry)"
    )

    target_date = score_date or date.today()
    is_forecast = target_date > date.today()

    where = "WHERE l.geometry IS NOT NULL"
    params: dict = {"target_date": target_date, "is_forecast": is_forecast}
    if state:
        where += " AND l.state ILIKE :state"
        params["state"] = f"%{state}%"

    sql = text(f"""
        SELECT
            l.id::text,
            l.name,
            l.state,
            {geom_expr}              AS geometry,
            r.score,
            r.level,
            r.incident_frequency_score  AS frequency_score,
            r.incident_trend_score      AS trend_score,
            r.news_sentiment_score      AS news_score
        FROM lgas l
        LEFT JOIN risk_scores r
            ON r.lga_id = l.id
            AND r.score_date = :target_date
            AND r.is_forecast = :is_forecast
        {where}
        ORDER BY l.state, l.name
    """)

    rows = (await db.execute(sql, params)).fetchall()

    features = []
    for row in rows:
        geom = json.loads(row.geometry) if row.geometry else None
        features.append({
            "type": "Feature",
            "id": row.id,
            "geometry": geom,
            "properties": {
                "name": row.name,
                "state": row.state,
                "score": row.score,
                "level": row.level,
                "frequency_score": row.frequency_score,
                "trend_score": row.trend_score,
                "news_score": row.news_score,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "score_date": str(target_date),
            "is_forecast": is_forecast,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "feature_count": len(features),
            "simplified": simplified,
        },
    }


@router.post("/forecast/run", tags=["risk"])
async def run_forecast(db: AsyncSession = Depends(get_db)):
    """Generate 7-day forecast scores from today's actuals."""
    from app.services.forecaster import generate_forecasts
    result = await generate_forecasts(db)
    return result


# ── National summary ────────────────────────────────────────────────────────

@router.get("/summary", response_model=NationalSummary)
async def get_national_summary(db: AsyncSession = Depends(get_db)):
    """
    National overview: score distribution, per-state breakdown,
    and 90-day incident totals.
    """
    dist_sql = text("""
        SELECT level, COUNT(*) AS cnt
        FROM risk_scores
        WHERE score_date = CURRENT_DATE AND is_forecast = false
        GROUP BY level
    """)
    dist_rows = (await db.execute(dist_sql)).fetchall()
    distribution = {r.level: r.cnt for r in dist_rows}
    for lvl in ("LOW", "MODERATE", "HIGH", "SEVERE"):
        distribution.setdefault(lvl, 0)

    state_sql = text("""
        SELECT
            l.state,
            COUNT(*)                                                   AS lga_count,
            SUM(CASE WHEN r.level = 'SEVERE'   THEN 1 ELSE 0 END)     AS severe,
            SUM(CASE WHEN r.level = 'HIGH'     THEN 1 ELSE 0 END)     AS high,
            SUM(CASE WHEN r.level = 'MODERATE' THEN 1 ELSE 0 END)     AS moderate,
            SUM(CASE WHEN r.level = 'LOW'      THEN 1 ELSE 0 END)     AS low,
            ROUND(AVG(r.score)::numeric, 1)                            AS avg_score,
            ROUND(MAX(r.score)::numeric, 1)                            AS max_score,
            (ARRAY_AGG(l.name ORDER BY r.score DESC NULLS LAST))[1]   AS top_lga,
            ROUND((MAX(r.score))::numeric, 1)                          AS top_lga_score
        FROM lgas l
        LEFT JOIN risk_scores r
            ON r.lga_id = l.id
            AND r.score_date = CURRENT_DATE
            AND r.is_forecast = false
        GROUP BY l.state
        ORDER BY max_score DESC NULLS LAST
    """)
    state_rows = (await db.execute(state_sql)).fetchall()
    states = [
        StateRiskSummary(
            state=r.state,
            lga_count=r.lga_count,
            severe=r.severe or 0,
            high=r.high or 0,
            moderate=r.moderate or 0,
            low=r.low or 0,
            avg_score=float(r.avg_score or 0),
            max_score=float(r.max_score or 0),
            top_lga=r.top_lga,
            top_lga_score=float(r.top_lga_score) if r.top_lga_score else None,
        )
        for r in state_rows
    ]

    incident_sql = text("""
        SELECT
            COUNT(*)                     AS total_incidents,
            COALESCE(SUM(fatalities), 0) AS total_fatalities
        FROM incidents
        WHERE event_date >= CURRENT_DATE - INTERVAL '90 days'
    """)
    inc = (await db.execute(incident_sql)).fetchone()

    news_sql = text("""
        SELECT COUNT(*) AS cnt
        FROM news_articles
        WHERE published_at >= NOW() - INTERVAL '7 days'
          AND security_relevant = true
    """)
    news_cnt = (await db.execute(news_sql)).scalar()

    return NationalSummary(
        score_date=date.today(),
        total_lgas=sum(distribution.values()),
        distribution=distribution,
        states=states,
        total_incidents_90d=int(inc.total_incidents),
        total_fatalities_90d=int(inc.total_fatalities),
        security_news_7d=int(news_cnt or 0),
    )


# ── Single LGA detail ───────────────────────────────────────────────────────

@router.get("/lga/{lga_id}", response_model=RiskScoreDetail)
async def get_lga_risk(lga_id: UUID, db: AsyncSession = Depends(get_db)):
    """Detailed risk score with full component breakdown for one LGA."""
    sql = text("""
        SELECT
            r.lga_id,
            l.name        AS lga_name,
            l.state,
            r.score,
            r.level,
            r.score_date,
            r.incident_frequency_score,
            r.incident_trend_score,
            r.news_sentiment_score,
            r.components,
            r.calculated_at
        FROM risk_scores r
        JOIN lgas l ON l.id = r.lga_id
        WHERE r.lga_id = :lga_id
          AND r.score_date = CURRENT_DATE
          AND r.is_forecast = false
    """)
    row = (await db.execute(sql, {"lga_id": lga_id})).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No risk score found for LGA {lga_id} today. Run the scorer first.",
        )

    components = None
    if row.components:
        raw = row.components
        cs = raw.get("component_scores", {})
        components = {
            "incident_count_90d": raw.get("incident_count_90d", 0),
            "fatalities_90d": raw.get("fatalities_90d", 0),
            "incidents_last_30d": raw.get("incidents_last_30d", 0),
            "incidents_prior_30d": raw.get("incidents_prior_30d", 0),
            "trend_direction": raw.get("trend_direction"),
            "trend_ratio": raw.get("trend_ratio"),
            "news_articles_7d": raw.get("news_articles_7d", 0),
            "avg_news_sentiment": raw.get("avg_news_sentiment"),
            "dominant_event_types": raw.get("dominant_event_types", []),
            "component_scores": {
                "frequency": cs.get("frequency", 0),
                "trend": cs.get("trend", 0),
                "news": cs.get("news", 0),
            },
        }

    return RiskScoreDetail(
        lga_id=row.lga_id,
        lga_name=row.lga_name,
        state=row.state,
        score=row.score,
        level=row.level,
        score_date=row.score_date,
        incident_frequency_score=row.incident_frequency_score,
        incident_trend_score=row.incident_trend_score,
        news_sentiment_score=row.news_sentiment_score,
        components=components,
        calculated_at=row.calculated_at,
    )


# ── State-level scores ──────────────────────────────────────────────────────

@router.get("/state/{state}", response_model=list[RiskScoreDetail])
async def get_state_risk(state: str, db: AsyncSession = Depends(get_db)):
    """Risk scores for all LGAs in a given state, sorted by score descending."""
    sql = text("""
        SELECT
            r.lga_id,
            l.name        AS lga_name,
            l.state,
            r.score,
            r.level,
            r.score_date,
            r.incident_frequency_score,
            r.incident_trend_score,
            r.news_sentiment_score,
            r.components,
            r.calculated_at
        FROM risk_scores r
        JOIN lgas l ON l.id = r.lga_id
        WHERE l.state ILIKE :state
          AND r.score_date = CURRENT_DATE
          AND r.is_forecast = false
        ORDER BY r.score DESC
    """)
    rows = (await db.execute(sql, {"state": f"%{state}%"})).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No scores found for state '{state}'")

    return [
        RiskScoreDetail(
            lga_id=r.lga_id,
            lga_name=r.lga_name,
            state=r.state,
            score=r.score,
            level=r.level,
            score_date=r.score_date,
            incident_frequency_score=r.incident_frequency_score,
            incident_trend_score=r.incident_trend_score,
            news_sentiment_score=r.news_sentiment_score,
            components=None,  # omit components in list view for brevity
            calculated_at=r.calculated_at,
        )
        for r in rows
    ]
