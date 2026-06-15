"""
ACLED sync orchestrator.

Flow:
  1. Determine last synced date from DB (max event_date in incidents table)
  2. Fetch all Nigeria incidents since that date via ACLEDClient
  3. Resolve each incident's LGA via LGAMatcher
  4. Bulk upsert into incidents table (conflict on acled_id → update)
"""
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.services.acled_client import ACLEDClient
from app.services.lga_matcher import LGAMatcher

logger = logging.getLogger(__name__)

# How far back to seed if the DB is empty
SEED_FROM_YEAR = 2010


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _row_to_upsert(row: dict, lga_id: str | None) -> dict:
    return {
        "acled_id": str(row.get("data_id", "")),
        "lga_id": lga_id,
        "event_date": _parse_date(row.get("event_date")),
        "event_type": row.get("event_type", ""),
        "sub_event_type": row.get("sub_event_type"),
        "actor1": row.get("actor1"),
        "actor2": row.get("actor2"),
        "inter1": row.get("inter1"),
        "inter2": row.get("inter2"),
        "region": row.get("region"),
        "country": row.get("country", "Nigeria"),
        "admin1": row.get("admin1"),
        "admin2": row.get("admin2"),
        "admin3": row.get("admin3"),
        "location": row.get("location"),
        "latitude": _safe_float(row.get("latitude")),
        "longitude": _safe_float(row.get("longitude")),
        "geo_precision": _safe_int(row.get("geo_precision"), default=None),
        "fatalities": _safe_int(row.get("fatalities")),
        "notes": row.get("notes"),
        "source": row.get("source"),
        "source_scale": row.get("source_scale"),
    }


async def _get_last_synced_date(db: AsyncSession) -> date | None:
    result = await db.execute(select(func.max(Incident.event_date)))
    return result.scalar_one_or_none()


async def _upsert_batch(db: AsyncSession, records: list[dict]) -> int:
    if not records:
        return 0

    stmt = (
        insert(Incident)
        .values(records)
        .on_conflict_do_update(
            index_elements=["acled_id"],
            set_={
                "lga_id": insert(Incident).excluded.lga_id,
                "event_date": insert(Incident).excluded.event_date,
                "event_type": insert(Incident).excluded.event_type,
                "sub_event_type": insert(Incident).excluded.sub_event_type,
                "actor1": insert(Incident).excluded.actor1,
                "actor2": insert(Incident).excluded.actor2,
                "fatalities": insert(Incident).excluded.fatalities,
                "notes": insert(Incident).excluded.notes,
                "source": insert(Incident).excluded.source,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
    return len(records)


async def run_acled_sync(db: AsyncSession, full_resync: bool = False) -> dict:
    """
    Main entry point for ACLED sync.

    Args:
        db: async DB session
        full_resync: if True, re-fetch from SEED_FROM_YEAR regardless of DB state

    Returns:
        Summary dict with counts and timing.
    """
    started_at = datetime.now(timezone.utc)

    if full_resync:
        since = date(SEED_FROM_YEAR, 1, 1)
        logger.info("Full resync from %s", since)
    else:
        last_date = await _get_last_synced_date(db)
        if last_date:
            since = last_date  # ACLED is >= so this re-fetches the last day (safe for upsert)
            logger.info("Incremental sync from last event_date=%s", since)
        else:
            since = date(SEED_FROM_YEAR, 1, 1)
            logger.info("No existing data — seeding from %s", since)

    matcher = LGAMatcher()
    await matcher.load(db)

    fetched = 0
    upserted = 0
    failed = 0
    BATCH_SIZE = 200

    async with ACLEDClient() as client:
        rows = await client.fetch_since_date(since)
        fetched = len(rows)
        logger.info("Fetched %d rows from ACLED", fetched)

        batch: list[dict] = []
        for row in rows:
            lga_id = await matcher.resolve(
                admin2=row.get("admin2"),
                admin1=row.get("admin1"),
                latitude=_safe_float(row.get("latitude")),
                longitude=_safe_float(row.get("longitude")),
                db=db,
            )
            try:
                record = _row_to_upsert(row, str(lga_id) if lga_id else None)
                if not record["event_date"]:
                    logger.warning("Skipping row with no event_date: %s", row.get("data_id"))
                    failed += 1
                    continue
                batch.append(record)
            except Exception as exc:
                logger.error("Error parsing row %s: %s", row.get("data_id"), exc)
                failed += 1
                continue

            if len(batch) >= BATCH_SIZE:
                upserted += await _upsert_batch(db, batch)
                batch = []

        if batch:
            upserted += await _upsert_batch(db, batch)

    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "fetched": fetched,
        "upserted": upserted,
        "failed": failed,
        "since": str(since),
        "duration_seconds": round(duration, 1),
    }
    logger.info("ACLED sync complete: %s", summary)
    return summary
