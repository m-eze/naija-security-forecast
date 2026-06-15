from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.incident import IncidentOut, IncidentsSummary, PaginatedIncidents

router = APIRouter(prefix="/incidents", tags=["incidents"])

PAGE_SIZE_MAX = 200


def _build_incident(row) -> IncidentOut:
    return IncidentOut(
        id=row.id,
        event_date=row.event_date,
        event_type=row.event_type,
        sub_event_type=row.sub_event_type,
        actor1=row.actor1,
        actor2=row.actor2,
        fatalities=row.fatalities,
        admin1=row.admin1,
        admin2=row.admin2,
        location=row.location,
        latitude=row.latitude,
        longitude=row.longitude,
        notes=row.notes,
        source=row.source,
        lga_id=row.lga_id,
    )


@router.get("", response_model=PaginatedIncidents)
async def list_incidents(
    state: str | None = Query(None, description="Filter by state (admin1)"),
    event_type: str | None = Query(None, description="e.g. 'Battles'"),
    days: int = Query(90, ge=1, le=3650, description="Lookback window in days"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """Paginated incident list, most recent first."""
    conditions = ["event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'"]
    params: dict = {
        "days": days,
        "offset": (page - 1) * page_size,
        "limit": page_size,
    }

    if state:
        conditions.append("admin1 ILIKE :state")
        params["state"] = f"%{state}%"
    if event_type:
        conditions.append("event_type ILIKE :event_type")
        params["event_type"] = f"%{event_type}%"

    where = "WHERE " + " AND ".join(conditions)

    total = (await db.execute(
        text(f"SELECT COUNT(*) FROM incidents {where}"), params
    )).scalar() or 0

    rows = (await db.execute(text(f"""
        SELECT id, event_date, event_type, sub_event_type,
               actor1, actor2, fatalities,
               admin1, admin2, location, latitude, longitude,
               notes, source, lga_id
        FROM incidents
        {where}
        ORDER BY event_date DESC
        LIMIT :limit OFFSET :offset
    """), params)).fetchall()

    return PaginatedIncidents(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_incident(r) for r in rows],
    )


@router.get("/summary", response_model=IncidentsSummary)
async def incidents_summary(
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate incident statistics over the given lookback window."""
    params = {"days": days}

    totals_row = (await db.execute(text("""
        SELECT COUNT(*) AS total, COALESCE(SUM(fatalities), 0) AS fatalities
        FROM incidents
        WHERE event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
    """), params)).fetchone()

    state_rows = (await db.execute(text("""
        SELECT
            admin1                              AS state,
            COUNT(*)                            AS incident_count,
            COALESCE(SUM(fatalities), 0)        AS total_fatalities,
            (ARRAY_AGG(event_type
                ORDER BY event_type))[1]        AS top_event_type
        FROM incidents
        WHERE event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
          AND admin1 IS NOT NULL
        GROUP BY admin1
        ORDER BY incident_count DESC
    """), params)).fetchall()

    type_rows = (await db.execute(text("""
        SELECT event_type, COUNT(*) AS cnt
        FROM incidents
        WHERE event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
        GROUP BY event_type
        ORDER BY cnt DESC
    """), params)).fetchall()

    return IncidentsSummary(
        total_incidents=int(totals_row.total),
        total_fatalities=int(totals_row.fatalities),
        date_range_days=days,
        by_state=[
            {
                "state": r.state,
                "incident_count": int(r.incident_count),
                "total_fatalities": int(r.total_fatalities),
                "top_event_type": r.top_event_type,
            }
            for r in state_rows
        ],
        by_event_type={r.event_type: int(r.cnt) for r in type_rows},
    )


@router.get("/lga/{lga_id}", response_model=PaginatedIncidents)
async def incidents_for_lga(
    lga_id: UUID,
    days: int = Query(365, ge=1, le=3650),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """All incidents for a specific LGA."""
    params = {
        "lga_id": lga_id,
        "days": days,
        "offset": (page - 1) * page_size,
        "limit": page_size,
    }
    total = (await db.execute(text("""
        SELECT COUNT(*) FROM incidents
        WHERE lga_id = :lga_id
          AND event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
    """), params)).scalar() or 0

    rows = (await db.execute(text("""
        SELECT id, event_date, event_type, sub_event_type,
               actor1, actor2, fatalities,
               admin1, admin2, location, latitude, longitude,
               notes, source, lga_id
        FROM incidents
        WHERE lga_id = :lga_id
          AND event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
        ORDER BY event_date DESC
        LIMIT :limit OFFSET :offset
    """), params)).fetchall()

    return PaginatedIncidents(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_incident(r) for r in rows],
    )


@router.get("/state/{state}", response_model=PaginatedIncidents)
async def incidents_for_state(
    state: str,
    days: int = Query(90, ge=1, le=3650),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_db),
):
    """All incidents in a state, most recent first."""
    params = {
        "state": f"%{state}%",
        "days": days,
        "offset": (page - 1) * page_size,
        "limit": page_size,
    }
    total = (await db.execute(text("""
        SELECT COUNT(*) FROM incidents
        WHERE admin1 ILIKE :state
          AND event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
    """), params)).scalar() or 0

    rows = (await db.execute(text("""
        SELECT id, event_date, event_type, sub_event_type,
               actor1, actor2, fatalities,
               admin1, admin2, location, latitude, longitude,
               notes, source, lga_id
        FROM incidents
        WHERE admin1 ILIKE :state
          AND event_date >= CURRENT_DATE - CAST(:days AS INTEGER) * INTERVAL '1 day'
        ORDER BY event_date DESC
        LIMIT :limit OFFSET :offset
    """), params)).fetchall()

    return PaginatedIncidents(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_incident(r) for r in rows],
    )
