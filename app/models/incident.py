import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.lga import LGA


# ACLED event type taxonomy for Nigeria
ACLED_EVENT_TYPES = [
    "Battles",
    "Violence against civilians",
    "Explosions/Remote violence",
    "Protests",
    "Riots",
    "Strategic developments",
]

ACLED_SUB_EVENT_TYPES = [
    "Armed clash",
    "Attack",
    "Suicide bomb",
    "Remote explosive/landmine/IED",
    "Shelling/artillery/missile attack",
    "Air/drone strike",
    "Abduction/forced disappearance",
    "Sexual violence",
    "Looting/property destruction",
    "Peaceful protest",
    "Violent demonstration",
    "Mob violence",
    "Government regains territory",
    "Non-state actor overtakes territory",
    "Headquarters or base established",
    "Agreement",
    "Arrest",
    "Change to group/activity",
]


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    lga_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lgas.id", ondelete="SET NULL"), nullable=True
    )

    # ACLED fields — acled_id allows deduplication on re-sync
    acled_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Actors
    actor1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inter1: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ACLED interaction code
    inter2: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Location (raw strings from ACLED, plus coordinates)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(50), nullable=False, default="Nigeria")
    admin1: Mapped[str | None] = mapped_column(String(100), nullable=True)  # State
    admin2: Mapped[str | None] = mapped_column(String(100), nullable=True)  # LGA
    admin3: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Town/ward
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_precision: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1=exact, 3=approx

    fatalities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_scale: Mapped[str | None] = mapped_column(String(50), nullable=True)

    lga: Mapped["LGA | None"] = relationship("LGA", back_populates="incidents")

    __table_args__ = (
        Index("ix_incidents_lga_id", "lga_id"),
        Index("ix_incidents_event_date", "event_date"),
        Index("ix_incidents_event_type", "event_type"),
        Index("ix_incidents_admin1", "admin1"),
        Index("ix_incidents_acled_id", "acled_id"),
    )

    def __repr__(self) -> str:
        return f"<Incident {self.event_type} on {self.event_date} @ {self.admin2}>"
