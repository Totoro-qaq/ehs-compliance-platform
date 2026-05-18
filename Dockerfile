FROM python:3.11-slim

# System dependencies:
# - poppler-utils for pdf2image
# - libgl1/libglib2.0-0 for PaddleOCR/OpenCV
# - antiword for legacy .doc extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    antiword \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
