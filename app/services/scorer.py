"""
Risk Score Engine — calculates a 0-100 composite risk score for every LGA.

Composite formula (weights sum to 1.0):
    score = 0.50 * frequency_score
          + 0.30 * trend_score
          + 0.20 * news_score

Component definitions
─────────────────────
frequency_score (0-100)
    Weighted incident count over last 90 days:
        raw = incident_count + fatalities * 2
    Normalized via 95th percentile across all LGAs so one extreme outlier
    (e.g. Maiduguri) does not compress every other LGA toward zero.

trend_score (0-100)
    Ratio of incidents in last 30 days vs prior 30 days (days 31-60):
        ratio = last_30d / max(prior_30d, 1)
    Maps: ratio > 2.0 → 90, 1.2-2.0 → 60-85, ~1.0 → 40, < 0.5 → 10
    LGAs with no recent incidents: 25 (slight unknown caution)

news_score (0-100)
    Average sentiment of security-relevant articles in last 7 days, inverted:
        score = (1 - avg_sentiment) * 50          # [-1,1] → [0,100]
    LGAs with no recent articles: 25 (neutral/unknown)

SecurityLevel thresholds
─────────────────────────
    LOW:      0  – 24.9
    MODERATE: 25 – 49.9
    HIGH:     50 – 74.9
    SEVERE:   75 – 100
"""
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_score import RiskScore, SecurityLevel

logger = logging.getLogger(__name__)

# ── Weights ────────────────────────────────────────────────────────────────
W_FREQUENCY = 0.50
W_TREND = 0.30
W_NEWS = 0.20

# ── Lookback windows ───────────────────────────────────────────────────────
FREQUENCY_DAYS = 90
TREND_RECENT_DAYS = 30
TREND_PRIOR_DAYS = 60   # days 31-60 back
NEWS_DAYS = 7

# ── Normalization ──────────────────────────────────────────────────────────
FREQUENCY_PERCENTILE = 95   # raw score at this percentile → maps to 100
NEUTRAL_SCORE = 25.0        # score for LGAs with no data


# ── Data containers ────────────────────────────────────────────────────────

@dataclass
class FreqRow:
    incident_count: int = 0
    total_fatalities: int = 0
    weighted_raw: float = 0.0
    dominant_event_types: list[str] = field(default_factory=list)


@dataclass
class TrendRow:
    last_30d: int = 0
    prior_30d: int = 0


@dataclass
class NewsRow:
    avg_sentiment: float = 0.0
    article_count: int = 0


# ── DB queries ─────────────────────────────────────────────────────────────

async def _fetch_frequency(db: AsyncSession, ref: date) -> dict[uuid.UUID, FreqRow]:
    since = ref - timedelta(days=FREQUENCY_DAYS)
    sql = text("""
        SELECT
            lga_id,
            COUNT(*)                         AS incident_count,
            COALESCE(SUM(fatalities), 0)     AS total_fatalities,
            COUNT(*) + COALESCE(SUM(fatalities), 0) * 2 AS weighted_raw
        FROM incidents
        WHERE event_date >= :since
          AND lga_id IS NOT NULL
        GROUP BY lga_id
    """)
    result = await db.execute(sql, {"since": since})
    return {
        row.lga_id: FreqRow(
            incident_count=int(row.incident_count),
            total_fatalities=int(row.total_fatalities),
            weighted_raw=float(row.weighted_raw),
        )
        for row in result
    }


async def _fetch_dominant_event_types(
    db: AsyncSession, ref: date
) -> dict[uuid.UUID, list[str]]:
    """Top 3 event types per LGA over last 90 days."""
    since = ref - timedelta(days=FREQUENCY_DAYS)
    sql = text("""
        SELECT lga_id, event_type, COUNT(*) AS cnt
        FROM incidents
        WHERE event_date >= :since AND lga_id IS NOT NULL
        GROUP BY lga_id, event_type
        ORDER BY lga_id, cnt DESC
    """)
    result = await db.execute(sql, {"since": since})
    out: dict[uuid.UUID, list[str]] = {}
    for row in result:
        out.setdefault(row.lga_id, [])
        if len(out[row.lga_id]) < 3:
            out[row.lga_id].append(row.event_type)
    return out


async def _fetch_trend(db: AsyncSession, ref: date) -> dict[uuid.UUID, TrendRow]:
    recent_start = ref - timedelta(days=TREND_RECENT_DAYS)
    prior_start = ref - timedelta(days=TREND_PRIOR_DAYS)
    sql = text("""
        SELECT
            lga_id,
            COUNT(CASE WHEN event_date >= :recent_start THEN 1 END) AS last_30d,
            COUNT(CASE WHEN event_date >= :prior_start
                        AND event_date < :recent_start THEN 1 END)  AS prior_30d
        FROM incidents
        WHERE event_date >= :prior_start
          AND lga_id IS NOT NULL
        GROUP BY lga_id
    """)
    result = await db.execute(sql, {
        "recent_start": recent_start,
        "prior_start": prior_start,
    })
    return {
        row.lga_id: TrendRow(
            last_30d=int(row.last_30d),
            prior_30d=int(row.prior_30d),
        )
        for row in result
    }


async def _fetch_news(db: AsyncSession, ref: date) -> dict[uuid.UUID, NewsRow]:
    since = ref - timedelta(days=NEWS_DAYS)
    sql = text("""
        SELECT
            lga_id,
            AVG(sentiment_score)  AS avg_sentiment,
            COUNT(*)              AS article_count
        FROM news_articles
        WHERE published_at >= :since
          AND security_relevant = true
          AND lga_id IS NOT NULL
        GROUP BY lga_id
    """)
    result = await db.execute(sql, {"since": since})
    return {
        row.lga_id: NewsRow(
            avg_sentiment=float(row.avg_sentiment),
            article_count=int(row.article_count),
        )
        for row in result
    }


async def _fetch_all_lga_ids(db: AsyncSession) -> list[uuid.UUID]:
    result = await db.execute(text("SELECT id FROM lgas"))
    return [row.id for row in result]


# ── Normalisation & scoring ─────────────────────────────────────────────────

def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (p / 100) * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _normalize_frequency(freq_map: dict[uuid.UUID, FreqRow]) -> dict[uuid.UUID, float]:
    """Map raw weighted scores → 0-100 using the 95th-percentile ceiling."""
    raws = [r.weighted_raw for r in freq_map.values() if r.weighted_raw > 0]
    if not raws:
        return {lga_id: 0.0 for lga_id in freq_map}

    ceiling = _percentile(raws, FREQUENCY_PERCENTILE)
    if ceiling == 0:
        ceiling = max(raws)

    return {
        lga_id: min(100.0, round(row.weighted_raw / ceiling * 100, 2))
        for lga_id, row in freq_map.items()
    }


def _trend_score(last_30d: int, prior_30d: int) -> float:
    """Convert last/prior incident counts to a 0-100 trend score."""
    if last_30d == 0 and prior_30d == 0:
        return NEUTRAL_SCORE

    ratio = last_30d / max(prior_30d, 1)

    if ratio >= 3.0:
        return 95.0
    elif ratio >= 2.0:
        return 80.0 + (ratio - 2.0) * 15.0   # 80 – 95
    elif ratio >= 1.2:
        return 50.0 + (ratio - 1.2) / 0.8 * 30.0  # 50 – 80
    elif ratio >= 0.8:
        return 30.0 + (ratio - 0.8) / 0.4 * 20.0  # 30 – 50
    elif ratio >= 0.5:
        return 15.0 + (ratio - 0.5) / 0.3 * 15.0  # 15 – 30
    else:
        return 5.0


def _news_score(avg_sentiment: float) -> float:
    """Convert average sentiment [-1, +1] → risk score [0, 100]."""
    # -1.0 (very negative news) → 100, 0.0 → 50, +1.0 (resolution) → 0
    return round((1.0 - avg_sentiment) * 50.0, 2)


def _composite(freq: float, trend: float, news: float) -> float:
    return round(W_FREQUENCY * freq + W_TREND * trend + W_NEWS * news, 2)


# ── Main scoring function ───────────────────────────────────────────────────

async def calculate_all_scores(db: AsyncSession) -> dict:
    """
    Calculate risk scores for every LGA and upsert into risk_scores table.

    Returns a summary dict.
    """
    ref = date.today()
    calculated_at = datetime.now(timezone.utc)

    logger.info("Fetching scoring data (reference date: %s)", ref)

    # Fetch all data in parallel would require multiple connections; run sequentially
    # (fast — all are single-pass aggregate queries)
    lga_ids = await _fetch_all_lga_ids(db)
    freq_map = await _fetch_frequency(db, ref)
    event_types_map = await _fetch_dominant_event_types(db, ref)
    trend_map = await _fetch_trend(db, ref)
    news_map = await _fetch_news(db, ref)

    logger.info(
        "Data fetched: %d LGAs, %d with incidents, %d with news",
        len(lga_ids), len(freq_map), len(news_map),
    )

    # Normalise frequency raw scores across all LGAs that have data
    freq_scores = _normalize_frequency(freq_map)

    records = []
    score_distribution = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "SEVERE": 0}

    for lga_id in lga_ids:
        freq_row = freq_map.get(lga_id, FreqRow())
        trend_row = trend_map.get(lga_id, TrendRow())
        news_row = news_map.get(lga_id)

        f_score = freq_scores.get(lga_id, 0.0)
        t_score = _trend_score(trend_row.last_30d, trend_row.prior_30d)
        n_score = _news_score(news_row.avg_sentiment) if news_row else NEUTRAL_SCORE

        composite = _composite(f_score, t_score, n_score)
        level = SecurityLevel.from_score(composite).value

        trend_ratio = (
            round(trend_row.last_30d / max(trend_row.prior_30d, 1), 2)
            if (trend_row.last_30d or trend_row.prior_30d)
            else None
        )

        components = {
            "incident_count_90d": freq_row.incident_count,
            "fatalities_90d": freq_row.total_fatalities,
            "weighted_raw": freq_row.weighted_raw,
            "incidents_last_30d": trend_row.last_30d,
            "incidents_prior_30d": trend_row.prior_30d,
            "trend_ratio": trend_ratio,
            "trend_direction": (
                "worsening" if trend_ratio and trend_ratio > 1.2
                else "improving" if trend_ratio and trend_ratio < 0.8
                else "stable"
            ),
            "news_articles_7d": news_row.article_count if news_row else 0,
            "avg_news_sentiment": round(news_row.avg_sentiment, 3) if news_row else None,
            "dominant_event_types": event_types_map.get(lga_id, []),
            "weights": {"frequency": W_FREQUENCY, "trend": W_TREND, "news": W_NEWS},
            "component_scores": {
                "frequency": f_score,
                "trend": t_score,
                "news": n_score,
            },
        }

        records.append({
            "lga_id": lga_id,
            "score_date": ref,
            "is_forecast": False,
            "score": composite,
            "level": level,
            "incident_frequency_score": f_score,
            "incident_trend_score": t_score,
            "news_sentiment_score": n_score,
            "components": components,
            "calculated_at": calculated_at,
        })

        score_distribution[level] += 1

    # Bulk upsert
    upserted = await _upsert_scores(db, records)

    summary = {
        "lgas_scored": len(records),
        "upserted": upserted,
        "score_date": str(ref),
        "distribution": score_distribution,
        "lgas_with_incident_data": len(freq_map),
        "lgas_with_news_data": len(news_map),
    }
    logger.info("Scoring complete: %s", summary)
    return summary


async def _upsert_scores(db: AsyncSession, records: list[dict]) -> int:
    if not records:
        return 0

    BATCH = 200
    total = 0

    for i in range(0, len(records), BATCH):
        batch = records[i : i + BATCH]
        stmt = (
            insert(RiskScore)
            .values(batch)
            .on_conflict_do_update(
                index_elements=["lga_id", "score_date", "is_forecast"],
                set_={
                    "score": insert(RiskScore).excluded.score,
                    "level": insert(RiskScore).excluded.level,
                    "incident_frequency_score": insert(RiskScore).excluded.incident_frequency_score,
                    "incident_trend_score": insert(RiskScore).excluded.incident_trend_score,
                    "news_sentiment_score": insert(RiskScore).excluded.news_sentiment_score,
                    "components": insert(RiskScore).excluded.components,
                    "calculated_at": insert(RiskScore).excluded.calculated_at,
                },
            )
        )
        await db.execute(stmt)
        total += len(batch)

    await db.commit()
    return total
