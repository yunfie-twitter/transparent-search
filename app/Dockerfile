FROM python:3.12-slim

WORKDIR /code

# Install system dependencies required for building some python packages (if any)
# and for healthchecks if needed, though pure python setup usually fine for basic dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command runs the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
