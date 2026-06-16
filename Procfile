web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
worker: celery -A app.workers.celery_app worker --loglevel=info
