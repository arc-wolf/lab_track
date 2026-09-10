# Multi-stage production Dockerfile for LabTrack
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for build & PDF generation (WeasyPrint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libffi-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final runtime image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.12/site-packages:$PYTHONPATH"

WORKDIR /app

# Install runtime library dependencies for Cairo/Pango/Fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /install
COPY . .

# Create non-root user for execution
RUN useradd -m -u 1000 labtrack && \
    mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R labtrack:labtrack /app

USER labtrack

EXPOSE 8000

# Default entrypoint using production Gunicorn config
CMD ["gunicorn", "-c", "gunicorn.conf.py", "config.wsgi:application"]
