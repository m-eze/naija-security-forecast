from datetime import date
from uuid import UUID

from pydantic import BaseModel


class IncidentOut(BaseModel):
    id: UUID
    event_date: date
    event_type: str
    sub_event_type: str | None
    actor1: str | None
    actor2: str | None
    fatalities: int
    admin1: str | None
    admin2: str | None
    location: str | None
    latitude: float | None
    longitude: float | None
    notes: str | None
    source: str | None
    lga_id: UUID | None

    model_config = {"from_attributes": True}


class PaginatedIncidents(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[IncidentOut]


class StateIncidentStat(BaseModel):
    state: str
    incident_count: int
    total_fatalities: int
    top_event_type: str | None


class IncidentsSummary(BaseModel):
    total_incidents: int
    total_fatalities: int
    date_range_days: int
    by_state: list[StateIncidentStat]
    by_event_type: dict[str, int]
