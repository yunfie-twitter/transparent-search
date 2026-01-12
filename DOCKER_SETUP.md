# Docker Compose Setup Guide

## Overview

This project uses Docker Compose to manage PostgreSQL, Redis, FastAPI backend, and React frontend services.

## Prerequisites

- Docker and Docker Compose installed
- Git repository cloned locally

## Quick Start

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

## Architecture

```
┌──────────────────────────────────────────┐
│         Docker Compose Network          │
│         (search_network - bridge)        │
├──────────────────────────────────────────┤
│                                          │
│  ┌─────────────┐  ┌─────────────┐      │
│  │  Frontend   │  │   Backend   │      │
│  │  :8081      │  │   :8080     │      │
│  └─────────────┘  └─────────────┘      │
│                        │                │
│                   ┌────┴────┐           │
│                   │          │           │
│            ┌──────────┐  ┌───────┐     │
│            │PostgreSQL│  │ Redis │     │
│            │  :5432   │  │ :6379 │     │
│            └──────────┘  └───────┘     │
│                                        │
└──────────────────────────────────────────┘

Host Machine:
  Frontend: http://localhost:8081
  Backend:  http://localhost:8080
```

## Service Details

### PostgreSQL
- **Image**: postgres:16-alpine
- **Container Name**: transparent-search-postgres
- **Default User**: postgres
- **Default Password**: postgres
- **Data**: Persisted in `postgres_data` volume
- **Network Access**: Internal (search_network only, no host port exposed)

### Redis
- **Image**: redis:7-alpine
- **Container Name**: transparent-search-redis
- **Data**: Persisted in `redis_data` volume
- **Network Access**: Internal (search_network only, no host port exposed)

### Backend (FastAPI)
- **Port**: 8080 (exposed to host)
- **Environment Variables**:
  - `DATABASE_URL`: PostgreSQL connection string with asyncpg driver
  - `REDIS_URL`: Redis connection string
  - `LOG_LEVEL`: INFO
  - `PYTHONUNBUFFERED`: 1

### Frontend (React)
- **Port**: 8081 (exposed to host)
- **Build Context**: ./frontend

## Database Initialization

### First Time Setup

When PostgreSQL starts for the first time (empty volume):

1. PostgreSQL initializes with `postgres` user
2. `/docker-entrypoint-initdb.d/01-init.sql` is automatically executed
3. `search_user` role is created
4. `transparent_search` database is created with `search_user` as owner

### Existing Database Setup

If you already have data in the `postgres_data` volume:

1. Start the containers:
   ```bash
   docker-compose up -d
   ```

2. Manually initialize the database (if needed):
   ```bash
   docker exec -i transparent-search-postgres psql -U postgres -f /docker-entrypoint-initdb.d/01-init.sql
   ```

3. Restart backend service:
   ```bash
   docker-compose restart transparent-search-backend
   ```

## Troubleshooting

### Issue: "Role search_user does not exist"

**Cause**: The PostgreSQL initialization script wasn't executed on an existing database.

**Solution**:
```bash
# Execute the init script
docker exec -i transparent-search-postgres psql -U postgres -f /docker-entrypoint-initdb.d/01-init.sql

# Restart backend
docker-compose restart transparent-search-backend
```

### Issue: Port already in use

**Cause**: Another service is using port 8080 or 8081.

**Solution**: Update port mappings in `docker-compose.yml`:
```yaml
backend:
  ports:
    - "8080:8080"  # Change first number to different port, e.g., "8090:8080"
```

### Issue: "asyncio extension requires an async driver"

**Cause**: Wrong database driver in requirements.txt (psycopg2 instead of asyncpg).

**Solution**: 
- Ensure `requirements.txt` uses `asyncpg` (not `psycopg2-binary`)
- Ensure `DATABASE_URL` uses `postgresql+asyncpg://` scheme

### Issue: Cannot connect to database

**Debug Steps**:
```bash
# Check if PostgreSQL is running
docker-compose ps

# Check PostgreSQL logs
docker-compose logs transparent-search-postgres

# Test connection from backend container
docker exec transparent-search-backend psql postgresql://search_user:search_password@postgres:5432/transparent_search
```

### Issue: Redis memory warning

**Message**: "Memory overcommit must be enabled! Without it..."

**This is a warning, not an error.** To suppress it:

```bash
# On your host machine
sudo sysctl vm.overcommit_memory=1

# To make permanent
sudo bash -c 'echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf'
```

## Network Security

**Important**: PostgreSQL and Redis ports are NOT exposed to the host machine. They are only accessible within the Docker network. This improves security by:
- Preventing unauthorized external access
- Avoiding port conflicts with other applications
- Following the principle of least privilege

If you need to connect to PostgreSQL from your host machine, use:
```bash
psql -h localhost -p 5432 -U postgres -d transparent_search
```

Note: This only works if you temporarily add port mappings to docker-compose.yml.

## Useful Commands

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f transparent-search-backend

# Execute shell in container
docker exec -it transparent-search-backend sh

# View database status
docker exec transparent-search-postgres pg_isready -U postgres

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Rebuild containers
docker-compose build --no-cache
```

## Environment Variables

For detailed environment variable configurations, see `.env.example`.
