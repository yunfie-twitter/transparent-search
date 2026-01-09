FROM python:3.12-slim

WORKDIR /code

# MeCab is enabled by default (mecab-python3 + unidic-lite).
# Install system libraries for MeCab to ensure runtime availability.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    mecab \
    libmecab-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
