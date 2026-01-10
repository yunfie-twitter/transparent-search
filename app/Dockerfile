FROM python:3.12-slim

WORKDIR /code

# Install system dependencies for MeCab
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code to /code/app
COPY . ./app

# Copy db initialization script
COPY ../db /code/db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8080/', timeout=5)" || exit 1

# Default command runs the API as a package with verbose logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
