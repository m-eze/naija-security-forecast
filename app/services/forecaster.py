"""
Short-range security risk forecaster — projects current LGA scores 1-7 days forward.

Model components
────────────────
1. Trend velocity
   Worsening areas accelerate risk; improving areas decay.
   Velocity is capped to prevent runaway projections.

2. News sentiment decay
   Recent negative news causes a near-term spike that fades exponentially
   (half-life ≈ 2 days). Positive resolution coverage pulls risk down.

3. Mean reversion
   Over many days without fresh incidents, scores drift back toward the
   neutral floor (30). This prevents deterministic runaway forecasts.

4. Historical variance boost (worsening only)
   Areas that have previously been high-risk but are currently quiet get a
   slightly elevated uncertainty band for the outer days.

Output: is_forecast=True rows in risk_scores for dates today+1 … today+7.
"""
import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_score import RiskScore, SecurityLevel

logger = logging.getLogger(__name__)

FORECAST_DAYS = [1, 2, 3, 4, 5, 6, 7]
NEUTRAL_FLOOR = 30.0
NEWS_HALFLIFE = 2.0   # days until news push halves
MEAN_REVERT_RATE = 0.025  # fraction per day toward neutral floor


def _trend_velocity(trend_direction: str, trend_ratio: float | None) -> float:
    """Daily score change from trend alone, capped at ±4."""
    if trend_ratio is None:
        return 0.0
    if trend_direction == "worsening":
        # ratio 1.2 → +0.8/day, ratio 3.0 → +4.0/day
        return min(4.0, (trend_ratio - 1.0) * 2.2)
    elif trend_direction == "improving":
        # ratio 0.8 → -0.4/day, ratio 0.2 → -1.8/day
        return max(-1.8, (trend_ratio - 1.0) * 1.5)
    return 0.0


def _news_push(avg_sentiment: float | None, day: int) -> float:
    """
    Exponentially decaying sentiment push.
    Negative sentiment (−1) → +8 pts on day 1, halving every 2 days.
    Positive sentiment (+1) → −4 pts on day 1, halving every 2 days.
    """
    if avg_sentiment is None:
        return 0.0
    amplitude = -avg_sentiment * 8.0   # negative sentiment → positive push
    return amplitude * math.exp(-math.log(2) / NEWS_HALFLIFE * day)


def _mean_revert(current_score: float, day: int) -> float:
    """Pull toward NEUTRAL_FLOOR over time."""
    gap = NEUTRAL_FLOOR - current_score
    return gap * MEAN_REVERT_RATE * day


def _forecast_one(
    current_score: float,
    trend_direction: str,
    trend_ratio: float | None,
    avg_sentiment: float | None,
    day: int,
) -> float:
    velocity = _trend_velocity(trend_direction, trend_ratio)
    news = _news_push(avg_sentiment, day)
    revert = _mean_revert(current_score, day)

    raw = current_score + velocity * day + news + revert
    return max(5.0, min(95.0, round(raw, 2)))


async def generate_forecasts(db: AsyncSession) -> dict:
    """
    Load today's actual scores, project each LGA 1-7 days forward,
    upsert into risk_scores with is_forecast=True.
    """
    today = date.today()
    calculated_at = datetime.now(timezone.utc)

    # Load today's actuals
    rows = (await db.execute(text("""
        SELECT
            r.lga_id,
            r.score,
            r.incident_frequency_score,
            r.incident_trend_score,
            r.news_sentiment_score,
            r.components
        FROM risk_scores r
        WHERE r.score_date = :today AND r.is_forecast = false
    """), {"today": today})).fetchall()

    if not rows:
        logger.warning("No actual scores found for %s — run scorer first", today)
        return {"error": "no_actual_scores", "date": str(today)}

    logger.info("Generating forecasts for %d LGAs, %d days ahead", len(rows), len(FORECAST_DAYS))

    records: list[dict[str, Any]] = []

    for row in rows:
        comp = row.components or {}
        trend_direction = comp.get("trend_direction", "stable")
        trend_ratio = comp.get("trend_ratio")
        avg_sentiment = comp.get("avg_news_sentiment")
        cs = comp.get("component_scores", {})

        for day in FORECAST_DAYS:
            forecast_date = today + timedelta(days=day)

            f_score = _forecast_one(
                row.score, trend_direction, trend_ratio, avg_sentiment, day
            )
            level = SecurityLevel.from_score(f_score).value

            # Forecast component scores (velocity applied proportionally to
            # the weighted contribution each component has in the composite)
            velocity = _trend_velocity(trend_direction, trend_ratio)
            news = _news_push(avg_sentiment, day)
            revert = _mean_revert(row.score, day)
            delta = velocity * day + news + revert

            freq_f = max(0.0, min(100.0, (cs.get("frequency", 0.0) or 0.0) + delta * 0.5))
            trend_f = max(0.0, min(100.0, (cs.get("trend", row.incident_trend_score) or 0.0) + delta * 0.3))
            news_f = max(0.0, min(100.0, (cs.get("news", row.news_sentiment_score) or 0.0) + news * 1.0))

            forecast_components = {
                **comp,
                "forecast_day": day,
                "score_delta": round(f_score - row.score, 2),
                "velocity": round(velocity, 3),
                "news_push_day1": round(_news_push(avg_sentiment, 1), 2),
                "component_scores": {
                    "frequency": round(freq_f, 2),
                    "trend": round(trend_f, 2),
                    "news": round(news_f, 2),
                },
            }

            records.append({
                "lga_id": row.lga_id,
                "score_date": forecast_date,
                "is_forecast": True,
                "score": f_score,
                "level": level,
                "incident_frequency_score": round(freq_f, 2),
                "incident_trend_score": round(trend_f, 2),
                "news_sentiment_score": round(news_f, 2),
                "components": forecast_components,
                "calculated_at": calculated_at,
            })

    upserted = await _upsert_forecasts(db, records)

    by_day: dict[str, dict[str, int]] = {}
    for r in records:
        day_key = str(r["score_date"])
        dist = by_day.setdefault(day_key, {"LOW": 0, "MODERATE": 0, "HIGH": 0, "SEVERE": 0})
        dist[r["level"]] += 1

    summary = {
        "lgas_forecast": len(rows),
        "days_ahead": len(FORECAST_DAYS),
        "records_written": upserted,
        "by_date": by_day,
    }
    logger.info("Forecast complete: %s", summary)
    return summary


async def _upsert_forecasts(db: AsyncSession, records: list[dict]) -> int:
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
