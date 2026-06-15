import uuid
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.lga import LGA


class SecurityLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"

    @classmethod
    def from_score(cls, score: float) -> "SecurityLevel":
        if score < 25:
            return cls.LOW
        elif score < 50:
            return cls.MODERATE
        elif score < 75:
            return cls.HIGH
        else:
            return cls.SEVERE


class RiskScore(Base, TimestampMixin):
    __tablename__ = "risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    lga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lgas.id", ondelete="CASCADE"), nullable=False
    )

    # The date this score represents (today for current, future date for forecast)
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Composite score 0–100 (higher = more dangerous)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # SecurityLevel enum value

    # Component scores (each 0–100) for transparency / explainability
    incident_frequency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    incident_trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full breakdown stored for audit/display
    # e.g. {
    #   "incident_count_90d": 12, "fatalities_90d": 34,
    #   "trend_direction": "worsening", "news_articles_7d": 5,
    #   "dominant_event_types": ["Battles", "Attack"]
    # }
    components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    lga: Mapped["LGA"] = relationship("LGA", back_populates="risk_scores")

    __table_args__ = (
        Index("ix_risk_scores_lga_id", "lga_id"),
        Index("ix_risk_scores_score_date", "score_date"),
        Index("ix_risk_scores_level", "level"),
        Index("ix_risk_scores_lga_date", "lga_id", "score_date", "is_forecast", unique=True),
    )

    def __repr__(self) -> str:
        return f"<RiskScore lga={self.lga_id} date={self.score_date} level={self.level}>"
