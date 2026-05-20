FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000


FROM base AS runtime

# Lightweight runtime: supports text-layer PDF, TXT, DOCX, CSV, and legacy DOC via antiword.
RUN apt-get update && apt-get install -y --no-install-recommends \
    antiword \
    && rm -rf /var/lib/apt/lists/*

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM runtime AS runtime-ocr

# Optional OCR runtime: add poppler and OpenCV/PaddleOCR dependencies for scanned PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-ocr.txt .
RUN pip install --no-cache-dir -r requirements-ocr.txt
