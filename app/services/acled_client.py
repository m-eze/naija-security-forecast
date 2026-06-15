"""
ACLED API client — uses email + access_key query-param authentication.

The access_key is found in your ACLED account settings at:
  acleddata.com → account → "Access Portal" or "API Access"

It is NOT the OAuth2 Bearer token from logging into the website.
"""
import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ACLED_BASE_URL = "https://acleddata.com/api/acled/read"
PAGE_SIZE = 500


class ACLEDError(Exception):
    pass


class ACLEDClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ACLEDClient":
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _auth_params(self) -> dict[str, str]:
        return {
            "email": settings.ACLED_EMAIL,
            "access_key": settings.ACLED_API_KEY,
        }

    async def _get_page(self, page: int, extra: dict[str, str]) -> dict:
        assert self._client
        params = {
            **self._auth_params(),
            "country": "Nigeria",
            "limit": str(PAGE_SIZE),
            "page": str(page),
            **extra,
        }
        resp = await self._client.get(ACLED_BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            raise ACLEDError(f"ACLED API error: {payload.get('error', payload)}")
        return payload

    async def fetch_incidents(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[dict]:
        """Fetch all Nigeria incidents, optionally filtered by date range."""
        extra: dict[str, str] = {}
        if since and until:
            extra["event_date"] = f"{since}|{until}"
            extra["event_date_where"] = "BETWEEN"
        elif since:
            extra["event_date"] = str(since)
            extra["event_date_where"] = ">="

        all_rows: list[dict] = []
        page = 1

        while True:
            logger.info("Fetching ACLED page %d (since=%s)", page, since)
            try:
                payload = await self._get_page(page, extra)
            except httpx.HTTPStatusError as exc:
                raise ACLEDError(f"HTTP {exc.response.status_code} from ACLED") from exc

            rows: list[dict] = payload.get("data", [])
            all_rows.extend(rows)
            logger.info("  → got %d rows (total so far: %d)", len(rows), len(all_rows))

            if len(rows) < PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(0.5)

        return all_rows

    async def fetch_since_date(self, since: date) -> list[dict]:
        return await self.fetch_incidents(since=since)
