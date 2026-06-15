# 🇳🇬 Naija Security Forecast

A "weather forecast for security" — a live, LGA-level risk dashboard for Nigeria that fuses historical incident data, news sentiment, and statistical trend models into a choropleth map anyone can read at a glance.

![Risk Map](https://img.shields.io/badge/coverage-775%20LGAs-green) ![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20Next.js-blue) ![Database](https://img.shields.io/badge/database-PostgreSQL%20%2B%20PostGIS-336791)

---

## What it does

| Feature | Detail |
|---|---|
| **Choropleth map** | All 775 Nigerian LGAs coloured LOW → MODERATE → HIGH → SEVERE |
| **7-day forecast** | Slide forward in time; scores extrapolate using trend velocity + news sentiment decay |
| **Incident type filters** | Kidnappings, school abductions, jihadist attacks, bombings, banditry, riots, protests, and more |
| **Live news feed** | Scrapes 10 Nigerian RSS sources; NLP classifies security relevance and sentiment |
| **State rankings** | Left sidebar ranks all 36 states + FCT by average risk score |
| **LGA detail panel** | Click any LGA on the map for a full score breakdown |

---

## Architecture

```
naija-security-forecast/
├── app/
│   ├── api/routes/          # FastAPI routers (risk, news, incidents, filters)
│   ├── core/                # DB engine, settings
│   ├── models/              # SQLAlchemy ORM (LGA, Incident, NewsArticle, RiskScore)
│   ├── schemas/             # Pydantic v2 response schemas
│   ├── services/
│   │   ├── acled_client.py  # ACLED API client (email + access_key auth)
│   │   ├── acled_sync.py    # Historical incident sync (from 2010)
│   │   ├── forecaster.py    # 7-day statistical forecast engine
│   │   ├── lga_matcher.py   # Fuzzy LGA name → PostGIS point-in-polygon matcher
│   │   ├── news_pipeline.py # Scrape → NLP → upsert pipeline
│   │   ├── nlp.py           # Keyword NLP: security classification + sentiment
│   │   ├── rss_scraper.py   # feedparser scraper for 10 Nigerian news sources
│   │   └── scorer.py        # Composite risk scoring engine
│   └── workers/             # Celery tasks + beat schedule
├── alembic/                 # DB migrations
├── scripts/                 # Manual trigger scripts
├── frontend/                # Next.js 16 app (see below)
└── main.py                  # FastAPI app entry point
```

### Risk score formula

```
score = 0.50 × frequency_score        # 90-day incident count, 95th-pct normalised
      + 0.30 × trend_score            # last-30d vs prior-30d ratio
      + 0.20 × news_sentiment_score   # inverted avg sentiment of local news
```

Thresholds: **LOW** < 25 · **MODERATE** < 50 · **HIGH** < 75 · **SEVERE** ≥ 75

### Forecast model

Each day's projection applies three signals to the current score:

- **Trend velocity** — worsening areas accelerate (up to +4 pts/day); improving areas decay
- **News sentiment decay** — negative coverage spikes risk near-term with a 2-day half-life
- **Mean reversion** — scores drift back toward the neutral floor (30) over time

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 async |
| Database | PostgreSQL 13 + PostGIS 3 · asyncpg driver |
| Migrations | Alembic |
| Background jobs | Celery + Redis |
| Frontend | Next.js 16 · TypeScript · Tailwind CSS |
| Map | Leaflet + react-leaflet |
| Data fetching | SWR |
| Incident data | ACLED (Armed Conflict Location & Event Data) |
| News sources | Punch, Vanguard, Guardian NG, ThisDay, Channels, Premium Times, Daily Post, HumAngle, Tribune, BusinessDay |

---

## Getting started

### Prerequisites

- Python 3.12
- Node.js 18+
- PostgreSQL 13+ with PostGIS extension
- Redis (for Celery workers)
- ACLED account with API access key → [acleddata.com](https://acleddata.com)

### Backend setup

```bash
# 1. Create virtualenv
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, ACLED_EMAIL, ACLED_API_KEY

# 4. Run migrations
alembic upgrade head

# 5. Seed LGA boundaries (downloads GADM 4.1 GeoJSON ~40 MB)
python scripts/seed_lgas.py

# 6. Sync historical ACLED incidents (2010 → today, takes ~10 min)
python scripts/run_acled_sync.py --full

# 7. Score all LGAs
python scripts/run_scorer.py

# 8. Generate 7-day forecasts
curl -X POST http://localhost:8001/api/risk/forecast/run

# 9. Start API server
uvicorn main:app --port 8001 --reload
```

### Frontend setup

```bash
cd frontend
npm install
npm run dev        # → http://localhost:3000
```

### Environment variables

```env
DATABASE_URL=postgresql+asyncpg://localhost:5432/naija_security
SYNC_DATABASE_URL=postgresql+psycopg2://localhost:5432/naija_security
REDIS_URL=redis://localhost:6379/0

ACLED_EMAIL=your@email.com
ACLED_API_KEY=your-acled-access-key   # from acleddata.com account settings

SECRET_KEY=change-me-in-production
ENVIRONMENT=development
```

> **Note:** `ACLED_API_KEY` is the alphanumeric key from your ACLED account settings page — not the OAuth2 JWT token from logging into the website.

### Recurring jobs (Celery)

```bash
# Start worker
celery -A app.workers.celery_app worker --loglevel=info

# Start beat scheduler (hourly news, daily scoring, weekly ACLED sync)
celery -A app.workers.celery_app beat --loglevel=info
```

Or trigger manually:

```bash
python scripts/run_scraper.py          # scrape news now
python scripts/run_scorer.py --report  # score + print distribution
python scripts/run_acled_sync.py       # incremental sync since last event
```

---

## API reference

| Endpoint | Description |
|---|---|
| `GET /api/risk/map` | All 775 LGAs with centroid + score (lightweight) |
| `GET /api/risk/geojson` | GeoJSON choropleth · `?score_date=YYYY-MM-DD` for forecasts |
| `GET /api/risk/summary` | National overview + per-state breakdown |
| `GET /api/risk/lga/{id}` | Full score breakdown for one LGA |
| `GET /api/risk/forecast/run` | Trigger 7-day forecast generation |
| `GET /api/news` | Paginated security news · `?state=&source=` |
| `GET /api/incidents` | Paginated incidents · `?state=&event_type=&days=` |
| `GET /api/incidents/filters` | Available incident type filter definitions |
| `GET /api/incidents/geojson` | Type-filtered choropleth · `?filter=kidnapping&days=365` |

Interactive docs: `http://localhost:8001/docs`

---

## Data sources

- **[ACLED](https://acleddata.com)** — Armed conflict events from 2010, updated weekly
- **[GADM 4.1](https://gadm.org)** — Nigeria Level 2 administrative boundaries (775 LGAs)
- **Nigerian news RSS** — 10 sources scraped hourly for security-relevant articles

---

## Roadmap

- [ ] ACLED API key activation and full historical sync
- [ ] ML-based risk model (replace statistical scorer with trained classifier)
- [ ] Mobile-responsive layout
- [ ] State-level drill-down page
- [ ] Export to PDF / shareable report
- [ ] Webhook alerts for LGAs crossing risk thresholds

---

## License

MIT
