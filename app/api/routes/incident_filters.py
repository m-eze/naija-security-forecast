"""
Incident-type filtered GeoJSON endpoint.

Each filter maps to a SQL predicate applied to the incidents table.
Predicates are pre-defined (not user-supplied) so injection is not a concern.
"""
import json
import math
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/incidents", tags=["incidents"])

# ── Filter registry ─────────────────────────────────────────────────────────
# Each value is a raw SQL predicate on the `incidents` table.

FILTERS: dict[str, dict[str, str]] = {
    "kidnapping": {
        "label": "Kidnappings",
        "icon": "⛓️",
        "sql": (
            "sub_event_type ILIKE '%abduction%' "
            "OR sub_event_type ILIKE '%kidnap%' "
            "OR notes ILIKE '%kidnap%'"
        ),
    },
    "school_abduction": {
        "label": "School Abductions",
        "icon": "🏫",
        "sql": (
            "(sub_event_type ILIKE '%abduction%' OR notes ILIKE '%kidnap%') "
            "AND (notes ILIKE '%school%' OR notes ILIKE '%student%' "
            "     OR notes ILIKE '%pupil%' OR notes ILIKE '%teacher%' "
            "     OR notes ILIKE '%college%')"
        ),
    },
    "jihadist": {
        "label": "Jihadist Attacks",
        "icon": "☪️",
        "sql": (
            "actor1 ILIKE '%boko haram%' OR actor1 ILIKE '%iswap%' "
            "OR actor1 ILIKE '%islamic state%' OR actor1 ILIKE '%ansaru%' "
            "OR actor1 ILIKE '%jnim%' "
            "OR actor2 ILIKE '%boko haram%' OR actor2 ILIKE '%iswap%'"
        ),
    },
    "explosion": {
        "label": "Bombings / IEDs",
        "icon": "💣",
        "sql": "event_type = 'Explosions/Remote violence'",
    },
    "civilian_attack": {
        "label": "Civilian Attacks",
        "icon": "🎯",
        "sql": "event_type = 'Violence against civilians'",
    },
    "battle": {
        "label": "Armed Clashes",
        "icon": "⚔️",
        "sql": "event_type = 'Battles'",
    },
    "banditry": {
        "label": "Banditry",
        "icon": "🐄",
        "sql": (
            "actor1 ILIKE '%bandit%' OR actor1 ILIKE '%fulani%' "
            "OR actor1 ILIKE '%pastoralist%' OR actor1 ILIKE '%herdsmen%' "
            "OR actor1 ILIKE '%herder%'"
        ),
    },
    "separatist": {
        "label": "Separatist Violence",
        "icon": "✊",
        "sql": (
            "actor1 ILIKE '%ipob%' OR actor1 ILIKE '%biafra%' "
            "OR actor1 ILIKE '%esn%' OR actor1 ILIKE '%massob%'"
        ),
    },
    "riot": {
        "label": "Riots",
        "icon": "🔥",
        "sql": "event_type = 'Riots'",
    },
    "protest": {
        "label": "Protests",
        "icon": "📢",
        "sql": "event_type = 'Protests'",
    },
}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 1.0
    s = sorted(values)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo) or 1.0


@router.get("/filters")
async def list_filters():
    """Return available incident type filter definitions for the frontend."""
    return [
        {"id": k, "label": v["label"], "icon": v["icon"]}
        for k, v in FILTERS.items()
    ]


@router.get("/geojson")
async def incident_geojson(
    filter: str = Query(..., description="Filter ID from /incidents/filters"),
    days: int = Query(365, ge=1, le=5000, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
):
    """
    GeoJSON choropleth coloured by density of a specific incident type.

    Score (0-100) is normalized using the 95th-percentile LGA count
    so rare but concentrated events still produce visible contrast.
    """
    if filter not in FILTERS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown filter '{filter}'. See /incidents/filters.")

    predicate = FILTERS[filter]["sql"]

    sql = text(f"""
        SELECT
            l.id::text                                                  AS id,
            l.name,
            l.state,
            ST_AsGeoJSON(ST_SimplifyPreserveTopology(l.geometry, 0.01)) AS geometry,
            COUNT(i.id)                                                  AS incident_count,
            COALESCE(SUM(i.fatalities), 0)                              AS total_fatalities
        FROM lgas l
        LEFT JOIN incidents i
            ON i.lga_id = l.id
            AND i.event_date >= CURRENT_DATE - CAST(:days AS INT) * INTERVAL '1 day'
            AND ({predicate})
        WHERE l.geometry IS NOT NULL
        GROUP BY l.id, l.name, l.state, l.geometry
        ORDER BY l.state, l.name
    """)

    rows = (await db.execute(sql, {"days": days})).fetchall()

    # Normalize counts to 0-100 using 95th-percentile ceiling
    counts = [float(r.incident_count) for r in rows if r.incident_count > 0]
    ceiling = _percentile(counts, 95) if counts else 1.0
    total_incidents = int(sum(counts))

    def score_from_count(c: int) -> float | None:
        if c == 0:
            return None
        return min(100.0, round(c / ceiling * 100, 1))

    def level_from_score(s: float | None) -> str | None:
        if s is None:
            return None
        if s >= 75:
            return "SEVERE"
        if s >= 50:
            return "HIGH"
        if s >= 25:
            return "MODERATE"
        return "LOW"

    features: list[dict[str, Any]] = []
    for row in rows:
        geom = json.loads(row.geometry) if row.geometry else None
        sc = score_from_count(row.incident_count)
        features.append({
            "type": "Feature",
            "id": row.id,
            "geometry": geom,
            "properties": {
                "name": row.name,
                "state": row.state,
                "score": sc,
                "level": level_from_score(sc),
                "incident_count": int(row.incident_count),
                "total_fatalities": int(row.total_fatalities),
                # Keep score/level fields consistent with composite GeoJSON schema
                "frequency_score": sc or 0.0,
                "trend_score": None,
                "news_score": None,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "filter": filter,
            "filter_label": FILTERS[filter]["label"],
            "days": days,
            "total_matching_incidents": total_incidents,
            "lgas_with_incidents": len(counts),
            "is_forecast": False,
        },
    }
