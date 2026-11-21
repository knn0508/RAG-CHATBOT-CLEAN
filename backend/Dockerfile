# syntax=docker/dockerfile:1
# ---- Stage 1: build wheels -------------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    PORT=5000 \
    DATABASE_FILE=/data/rag_chatbot.db \
    CONTACTS_DB_FILE=/data/contacts.db \
    VECTOR_DB_PATH=/data/chroma_db \
    UPLOAD_FOLDER=/data/documents \
    SESSION_FILE_DIR=/data/flask_session
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && rm -rf /wheels
COPY --chown=app:app backend/ /app/backend/
COPY --chown=app:app example_docs/ /app/example_docs/
WORKDIR /app/backend
USER app
VOLUME ["/data"]
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"5000\")}/api/health')"
# One worker + threads: SQLite and the Chroma persistent client are not multi-process safe.
CMD ["sh", "-c", "exec gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120"]
