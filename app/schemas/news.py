from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NewsArticleOut(BaseModel):
    id: UUID
    headline: str
    url: str
    source: str
    published_at: datetime | None
    sentiment_score: float | None
    sentiment_label: str | None
    extracted_state: str | None
    extracted_lga: str | None
    extracted_entities: dict | None
    lga_id: UUID | None

    model_config = {"from_attributes": True}


class PaginatedNews(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[NewsArticleOut]
