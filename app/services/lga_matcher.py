"""
Resolves ACLED's free-text admin2 field to a canonical LGA row in the DB.

Strategy (in order):
  1. Exact match on normalized name within the same state
  2. Fuzzy match (difflib) — threshold 0.82
  3. Coordinate-based PostGIS lookup if geometry is loaded
  4. None — incident stored without lga_id
"""
import logging
import re
import uuid
from difflib import SequenceMatcher

from geoalchemy2.functions import ST_Contains, ST_SetSRID, ST_MakePoint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lga import LGA

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.82


def _normalize(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[-_/]", " ", name)
    name = re.sub(r"\s+", " ", name)
    # strip common suffixes that vary between datasets
    for suffix in (" lga", " local government area", " lg"):
        name = name.removesuffix(suffix)
    return name.strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class LGAMatcher:
    """Cache-backed LGA resolver. Load once per sync run, reuse across rows."""

    def __init__(self) -> None:
        # (normalized_name, state) -> lga_id
        self._cache: dict[tuple[str, str], uuid.UUID] = {}
        # normalized_name -> list of (lga_id, normalized_state)  for fuzzy fallback
        self._all: list[tuple[str, str, uuid.UUID]] = []
        self._loaded = False

    async def load(self, db: AsyncSession) -> None:
        result = await db.execute(select(LGA.id, LGA.name, LGA.state))
        rows = result.all()
        for lga_id, name, state in rows:
            norm_name = _normalize(name)
            norm_state = _normalize(state)
            self._cache[(norm_name, norm_state)] = lga_id
            self._all.append((norm_name, norm_state, lga_id))
        self._loaded = True
        logger.info("LGAMatcher loaded %d LGAs", len(rows))

    def _exact(self, admin2: str, admin1: str) -> uuid.UUID | None:
        return self._cache.get((_normalize(admin2), _normalize(admin1)))

    def _fuzzy(self, admin2: str, admin1: str) -> uuid.UUID | None:
        norm_a2 = _normalize(admin2)
        norm_a1 = _normalize(admin1)
        best_score = 0.0
        best_id: uuid.UUID | None = None

        for norm_name, norm_state, lga_id in self._all:
            if norm_state != norm_a1:
                continue
            score = _similarity(norm_a2, norm_name)
            if score > best_score:
                best_score = score
                best_id = lga_id

        if best_score >= FUZZY_THRESHOLD:
            logger.debug(
                "Fuzzy match '%s' → id=%s (score=%.2f)", admin2, best_id, best_score
            )
            return best_id
        return None

    async def resolve(
        self,
        admin2: str | None,
        admin1: str | None,
        latitude: float | None = None,
        longitude: float | None = None,
        db: AsyncSession | None = None,
    ) -> uuid.UUID | None:
        if not self._loaded:
            raise RuntimeError("Call LGAMatcher.load(db) before resolving")

        if admin2 and admin1:
            lga_id = self._exact(admin2, admin1)
            if lga_id:
                return lga_id
            lga_id = self._fuzzy(admin2, admin1)
            if lga_id:
                return lga_id

        # PostGIS point-in-polygon fallback
        if latitude and longitude and db:
            point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            result = await db.execute(
                select(LGA.id).where(ST_Contains(LGA.geometry, point)).limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                logger.debug(
                    "Coordinate match (%.4f, %.4f) → lga_id=%s", latitude, longitude, row
                )
                return row

        logger.debug("No LGA match for admin2='%s' admin1='%s'", admin2, admin1)
        return None
