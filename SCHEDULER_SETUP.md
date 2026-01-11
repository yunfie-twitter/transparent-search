# Crawl Scheduler Setup & Integration Guide

## Installation

### Requirements
```bash
pip install apscheduler
```

## FastAPI Integration

### 1. Update `main.py` or `app.py`

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.background_scheduler import (
    start_background_scheduler,
    stop_background_scheduler,
)
from app.routers import scheduler_admin

# Lifespan context
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await start_background_scheduler()
    yield
    # Shutdown
    await stop_background_scheduler()

app = FastAPI(lifespan=lifespan)

# Include scheduler admin routes
app.include_router(scheduler_admin.router)
```

### 2. Install Router

Add to `app/routers/__init__.py` or wherever you register routers:

```python
from app.routers import scheduler_admin
app.include_router(scheduler_admin.router)
```

## API Endpoints

### 🔍 Auto-Discovery

**Discover all sites and schedule crawls automatically:**

```bash
curl -X POST \
  "http://localhost:8000/api/admin/scheduler/discover-all?token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "success",
  "message": "Scheduled 15 crawls",
  "sites_found": 20,
  "crawls_scheduled": 15,
  "sites_skipped": 5,
  "scheduled": [
    {
      "domain": "momon-ga.com",
      "session_id": "sess_abc123",
      "job_id": "job_xyz789"
    }
  ]
}
```

### 🛑 Force Stop All

**Immediately stop all crawling operations:**

```bash
curl -X POST \
  "http://localhost:8000/api/admin/scheduler/force-stop?confirm=true&token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "force_stopped",
  "message": "All crawls have been forcefully stopped",
  "timestamp": "2026-01-12T04:20:00.000000"
}
```

### ⏸️ Force Pause Indexing

**Pause indexing while allowing crawling to continue:**

```bash
curl -X POST \
  "http://localhost:8000/api/admin/scheduler/force-pause-index?confirm=true&token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "index_paused",
  "message": "All indexing operations have been paused",
  "timestamp": "2026-01-12T04:20:00.000000"
}
```

### ▶️ Resume All Operations

**Resume after force stop/pause:**

```bash
curl -X POST \
  "http://localhost:8000/api/admin/scheduler/resume?token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "resumed",
  "message": "All operations resumed",
  "timestamp": "2026-01-12T04:20:00.000000"
}
```

### 📊 Get Status

**Check current scheduler status:**

```bash
curl -X GET \
  "http://localhost:8000/api/admin/scheduler/status?token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "ok",
  "scheduler": {
    "crawl_enabled": true,
    "index_enabled": true,
    "force_stop": false,
    "force_pause_index": false,
    "min_interval_hours": 4,
    "max_interval_hours": 24
  }
}
```

### 📋 Manual Queue Processing

**Manually trigger crawl queue processing:**

```bash
curl -X POST \
  "http://localhost:8000/api/admin/scheduler/process-queue?limit=100&token=YOUR_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "success",
  "result": {
    "status": "success",
    "processed": 25,
    "remaining_jobs": 150
  }
}
```

## Background Tasks

### Automatic Tasks

Once the background scheduler starts, these tasks run automatically:

#### 1. **Auto-Discovery (every 6 hours)**
   - Discovers all sites in database
   - Checks if they've been crawled in past 24 hours
   - Auto-detects sitemaps
   - Creates crawl jobs for new/stale sites
   - Random interval: 4-24 hours between crawls

#### 2. **Queue Processing (every 30 seconds)**
   - Processes pending crawl jobs
   - Indexes completed crawl results
   - Respects force-stop and pause flags
   - Handles errors gracefully

#### 3. **Random Scheduling (every 12 hours)**
   - Reschedules sites with random intervals
   - Ensures distributed load
   - Prevents thundering herd

## Configuration

### Adjust Intervals

Edit `app/services/crawl_scheduler.py`:

```python
class CrawlScheduler:
    # Scheduling configuration
    MIN_CRAWL_INTERVAL_HOURS = 4      # Minimum time between crawls
    MAX_CRAWL_INTERVAL_HOURS = 24     # Maximum time between crawls
```

Edit `app/services/background_scheduler.py`:

```python
# Auto-discovery every 6 hours
cls._scheduler.add_job(
    cls._auto_discover_sites_task,
    trigger=IntervalTrigger(hours=6),  # Change this
    ...
)

# Queue processing every 30 seconds
cls._scheduler.add_job(
    cls._process_queue_task,
    trigger=IntervalTrigger(seconds=30),  # Change this
    ...
)
```

## Workflow

```
┌─────────────────────────────────────────────────┐
│  FastAPI Startup                                │
│  ↓                                              │
│  background_scheduler.start()                   │
│  ↓                                              │
│  APScheduler initialized                        │
│  ↓                                              │
│  ┌─────────────────────────────────────────┐   │
│  │ Background Tasks (Continuous)            │   │
│  │                                         │   │
│  │ ⏰ Every 6 hours:                       │   │
│  │   discover_and_schedule_sites()        │   │
│  │                                         │   │
│  │ ⏰ Every 30 seconds:                    │   │
│  │   process_crawl_queue()                │   │
│  │   → Crawl pending jobs                 │   │
│  │   → Index completed results            │   │
│  │                                         │   │
│  │ ⏰ Every 12 hours:                      │   │
│  │   schedule_random_crawls()             │   │
│  │                                         │   │
│  └─────────────────────────────────────────┘   │
│  ↓                                              │
│  (Can also use manual API endpoints)            │
│  ↓                                              │
│  POST /admin/scheduler/discover-all             │
│  POST /admin/scheduler/force-stop               │
│  POST /admin/scheduler/force-pause-index        │
│  POST /admin/scheduler/resume                   │
│  GET /admin/scheduler/status                    │
│  ↓                                              │
│  FastAPI Shutdown                               │
│  ↓                                              │
│  background_scheduler.stop()                    │
│  ↓                                              │
│  APScheduler gracefully shut down               │
└─────────────────────────────────────────────────┘
```

## Monitoring

### Check Running Jobs

```python
from app.services.background_scheduler import background_scheduler

jobs = background_scheduler.get_jobs()
for job in jobs:
    print(f"{job['name']}: Next run at {job['next_run_time']}")
```

### Log Levels

Enable debug logging to see scheduler activity:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Troubleshooting

### Scheduler not starting

- Check FastAPI lifespan context is properly configured
- Verify APScheduler is installed: `pip install apscheduler`
- Check logs for error messages

### Too many crawls scheduled

- Adjust `MIN_CRAWL_INTERVAL_HOURS` and `MAX_CRAWL_INTERVAL_HOURS`
- Reduce discovery frequency from 6 hours to longer interval
- Use `force_stop` to pause and review

### Crawls not starting

- Check if force-stop is active: `GET /admin/scheduler/status`
- Verify crawl jobs are being created: Check database
- Check logs for crawler service errors

## Summary

✅ **Fully autonomous** - No manual intervention needed  
✅ **Manual override** - Can trigger/stop via API  
✅ **Graceful control** - Force stop/pause operations  
✅ **Random scheduling** - Distributed load across time  
✅ **Respects limits** - Configurable intervals  
✅ **Error handling** - Graceful degradation  
