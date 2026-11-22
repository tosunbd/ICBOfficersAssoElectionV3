# ICB Election API — FastAPI + OpenCV ballot reader
#
# No Tesseract / poppler needed: PDF pages are rendered with pypdfium2 (bundled
# PDFium) and marks are detected with OpenCV.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libglib is needed by opencv-python-headless; curl is used by the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# Runtime data (SQLite DB, Scanned/Completed/Failed/Previews) lives in /app/data,
# which docker-compose mounts from the host so files survive container rebuilds.
RUN mkdir -p /app/data/Scanned /app/data/Completed /app/data/Failed /app/data/Previews \
    && useradd --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
