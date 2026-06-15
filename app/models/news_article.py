import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.lga import LGA


NEWS_SOURCES = [
    "Punch",
    "Vanguard",
    "Premium Times",
    "Daily Trust",
    "ThisDay",
    "The Guardian Nigeria",
    "Tribune",
    "Channels TV",
    "NAN",           # News Agency of Nigeria
    "SaharaReporters",
    "HumAngle",      # conflict-focused outlet
    "Other",
]


class NewsArticle(Base, TimestampMixin):
    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    lga_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lgas.id", ondelete="SET NULL"), nullable=True
    )

    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Geographic resolution from NLP extraction
    extracted_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_lga: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # NLP outputs
    security_relevant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # -1.0 (very negative) to 1.0 (very positive)
    sentiment_label: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # negative / neutral / positive

    # Extracted entities and event types as JSON for flexibility
    # e.g. {"event_types": ["attack", "kidnapping"], "actors": ["Boko Haram"]}
    extracted_entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Raw scrape metadata
    scrape_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending / processed / failed

    lga: Mapped["LGA | None"] = relationship("LGA", back_populates="news_articles")

    __table_args__ = (
        Index("ix_news_lga_id", "lga_id"),
        Index("ix_news_published_at", "published_at"),
        Index("ix_news_source", "source"),
        Index("ix_news_security_relevant", "security_relevant"),
        Index("ix_news_extracted_state", "extracted_state"),
    )

    def __repr__(self) -> str:
        return f"<NewsArticle '{self.headline[:60]}' from {self.source}>"
