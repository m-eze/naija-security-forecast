from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import risk, news, incidents
from app.api.routes import incident_filters

app = FastAPI(
    title="Naija Security Forecast",
    description="Statistical security situation forecast for Nigeria — LGA-level risk index.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(incident_filters.router, prefix="/api")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "0.1.0"}
