import uuid
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import String, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.news_article import NewsArticle
    from app.models.risk_score import RiskScore


NIGERIA_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi",
    "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo",
    "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]


class LGA(Base, TimestampMixin):
    __tablename__ = "lgas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    # Official NBS/INEC LGA code e.g. "NGA001001"
    lga_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PostGIS MultiPolygon for LGA boundary
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    # Centroid for quick point-in-polygon queries
    centroid: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="lga", lazy="select"
    )
    news_articles: Mapped[list["NewsArticle"]] = relationship(
        "NewsArticle", back_populates="lga", lazy="select"
    )
    risk_scores: Mapped[list["RiskScore"]] = relationship(
        "RiskScore", back_populates="lga", lazy="select"
    )

    __table_args__ = (
        Index("ix_lgas_state", "state"),
        Index("ix_lgas_name_state", "name", "state", unique=True),
        # GeoAlchemy2 auto-creates idx_lgas_geometry and idx_lgas_centroid (GiST)
    )

    def __repr__(self) -> str:
        return f"<LGA {self.name}, {self.state}>"
