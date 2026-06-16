FROM python:3.12-slim

WORKDIR /app

# libpq-dev: needed by psycopg2-binary at runtime
# gcc: needed to compile some asyncpg/lxml wheels if pre-built aren't available
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

# Railway injects $PORT; fall back to 8001 for local docker runs
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
