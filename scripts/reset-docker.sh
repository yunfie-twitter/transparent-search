#!/bin/bash
# Reset Docker containers and volumes for fresh start

set -e

echo "🗑️  Resetting Docker environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
    echo -e "${RED}❌ docker-compose not found${NC}"
    exit 1
fi

# Determine docker-compose command
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
else
    DC="docker compose"
fi

echo -e "${YELLOW}⏹️  Stopping containers...${NC}"
$DC down --remove-orphans || true

echo -e "${YELLOW}🗑️  Removing PostgreSQL volume...${NC}"
docker volume rm transparent-search_postgres_data || true

echo -e "${YELLOW}🗑️  Removing Redis volume...${NC}"
docker volume rm transparent-search_redis_data || true

echo -e "${GREEN}✅ Volumes removed${NC}"

echo -e "${YELLOW}🚀 Starting fresh containers...${NC}"
$DC up -d

echo -e "${YELLOW}⏳ Waiting for PostgreSQL to initialize (30 seconds)...${NC}"
sleep 30

echo -e "${YELLOW}🔍 Checking PostgreSQL health...${NC}"
$DC logs postgres | tail -20

echo -e "${YELLOW}⏳ Waiting for Backend to start (30 seconds)...${NC}"
sleep 30

echo -e "${YELLOW}🔍 Checking Backend logs...${NC}"
$DC logs backend | tail -30

echo -e "${GREEN}✅ Reset complete!${NC}"
echo ""
echo "Services running:"
echo "  - Frontend: http://localhost:8081"
echo "  - Backend API: http://localhost:8080"
echo "  - Backend Docs: http://localhost:8080/api/docs"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo ""
echo "To view logs:"
echo "  $DC logs -f backend"
echo "  $DC logs -f postgres"
echo "  $DC logs -f redis"
