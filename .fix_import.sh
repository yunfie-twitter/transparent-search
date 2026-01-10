#!/bin/bash
# Fix import errors and restart containers

echo "🔧 Fixing import issues..."

# Stop running containers
echo "⏹️  Stopping containers..."
docker-compose down

# Clear Python cache
echo "🗑️  Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Clear Redis cache
echo "🗑️  Clearing Redis cache..."
docker-compose exec redis redis-cli FLUSHALL 2>/dev/null || echo "Redis not running, skipping..."

# Rebuild images
echo "🏗️  Rebuilding images..."
docker-compose build --no-cache

# Start containers
echo "🚀 Starting containers..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Check health
echo "✅ Checking health..."
docker-compose ps

echo "✅ Done! Checking API..."
sleep 2
curl -s http://localhost:8080/health | jq . || echo "API not ready yet, check logs"

echo ""
echo "📋 View logs with: docker-compose logs -f api"
