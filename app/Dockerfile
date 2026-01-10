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

# Default command runs the API as a package with verbose logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
