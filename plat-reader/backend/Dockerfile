# Standalone Plat Reader Container
FROM python:3.11-slim

# Install system utilities for PDF rasterization and OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy standalone components
COPY engine/ ./engine/
COPY plat_curves/ ./plat_curves/
COPY scripts/ ./scripts/
COPY backend/ ./backend/
COPY widget/ ./widget/
COPY sample/ ./sample/

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PLAT_READER_ALLOWED_ORIGINS=*

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8000"]
