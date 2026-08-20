FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and src first for better caching
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Copy rest of application
COPY . .

# Create data directory
RUN mkdir -p /data

EXPOSE 3000

# Data dir: set here so the container always writes to /data (mounted volume).
# Local/dev runs use the relative ./data default in the image source.
ENV DATA_DIR=/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

CMD ["python", "main.py"]
