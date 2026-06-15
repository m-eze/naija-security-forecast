from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ComponentScores(BaseModel):
    frequency: float
    trend: float
    news: float


class RiskComponents(BaseModel):
    incident_count_90d: int
    fatalities_90d: int
    incidents_last_30d: int
    incidents_prior_30d: int
    trend_direction: str | None
    trend_ratio: float | None
    news_articles_7d: int
    avg_news_sentiment: float | None
    dominant_event_types: list[str]
    component_scores: ComponentScores


class RiskScoreSummary(BaseModel):
    score: float
    level: str
    score_date: date


class RiskScoreDetail(RiskScoreSummary):
    lga_id: UUID
    lga_name: str
    state: str
    incident_frequency_score: float | None
    incident_trend_score: float | None
    news_sentiment_score: float | None
    components: RiskComponents | None
    calculated_at: datetime

    model_config = {"from_attributes": True}


class LGAMapPoint(BaseModel):
    id: UUID
    name: str
    state: str
    lng: float | None
    lat: float | None
    score: float | None
    level: str | None


class MapResponse(BaseModel):
    score_date: date
    lgas: list[LGAMapPoint]
    total: int


class GeoFeatureProperties(BaseModel):
    name: str
    state: str
    score: float | None
    level: str | None
    frequency_score: float | None
    trend_score: float | None
    news_score: float | None


class GeoFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: Any
    properties: GeoFeatureProperties


class GeoJSONResponse(BaseModel):
    type: str = "FeatureCollection"
    features: list[GeoFeature]
    metadata: dict


class StateRiskSummary(BaseModel):
    state: str
    lga_count: int
    severe: int
    high: int
    moderate: int
    low: int
    avg_score: float
    max_score: float
    top_lga: str | None
    top_lga_score: float | None


class NationalSummary(BaseModel):
    score_date: date
    total_lgas: int
    distribution: dict[str, int]
    states: list[StateRiskSummary]
    total_incidents_90d: int
    total_fatalities_90d: int
    security_news_7d: int
