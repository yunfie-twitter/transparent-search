# Project Structure

## Directory Overview

```
transparent-search/
├── app/                          # Main application code
│   ├── __init__.py
│   ├── api/                      # API route definitions
│   │   ├── __init__.py
│   │   ├── crawler_router.py     # Crawler endpoints (POST /crawl/*)
│   │   └── router.py             # Main router that combines all routes
│   ├── core/                     # Core application utilities
│   │   ├── __init__.py
│   │   ├── config.py             # Configuration management
│   │   ├── database.py           # Database connection setup
│   │   ├── exceptions.py         # Custom exception definitions
│   │   ├── exception_handlers.py # Global exception handlers
│   │   └── logging.py            # Logging configuration
│   ├── db/                       # Database layer
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── database.py           # Database session management
│   │   └── seeds.py              # Test data seeding
│   ├── middleware/               # FastAPI middleware
│   │   ├── __init__.py
│   │   ├── logging_middleware.py
│   │   ├── rate_limit_middleware.py
│   │   ├── request_id_middleware.py
│   │   └── security_headers_middleware.py
│   ├── routers/                  # Additional API routers
│   │   ├── __init__.py
│   │   ├── search.py             # Search endpoints
│   │   ├── advanced_search.py    # Advanced search
│   │   ├── admin.py              # Admin endpoints
│   │   ├── admin_crawl.py        # Admin crawl management
│   │   ├── analytics.py          # Analytics endpoints
│   │   ├── click.py              # Click tracking
│   │   ├── images.py             # Image endpoints
│   │   └── suggest.py            # Autocomplete suggestions
│   └── services/                 # Business logic
│       ├── __init__.py
│       └── crawler.py            # Crawling service implementation
├── alembic/                      # Database migrations (Alembic)
│   ├── env.py                    # Migration environment config
│   ├── script.py.mako            # Migration template
│   └── versions/                 # Migration files
│       ├── 001_initial.py        # Initial schema
│       ├── 002_add_indexes.py    # Performance indexes
│       └── 003_add_search_tables.py  # Search tables (NEW)
├── docs/                         # Documentation
│   ├── DATABASE_MIGRATION.md     # Migration guide
│   └── PROJECT_STRUCTURE.md      # This file
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── conftest.py               # Pytest configuration
│   ├── test_api.py
│   ├── test_crawler.py
│   └── test_database.py
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── Dockerfile                    # Container definition
├── docker-compose.yml            # Multi-container setup
├── alembic.ini                   # Alembic configuration
├── main.py                       # Application entry point
├── requirements.txt              # Python dependencies
├── README.md                     # Project documentation
├── CHANGELOG.md                  # Version history
└── CONTRIBUTING.md               # Contribution guidelines
```

## Key Components

### `main.py` - Application Entry Point

Initializes FastAPI app and registers routers:

```python
app = FastAPI()
app.include_router(router, prefix="/api")
```

### `app/core/` - Core Infrastructure

| File | Purpose |
|------|----------|
| `config.py` | Settings from environment variables |
| `database.py` | PostgreSQL/AsyncIO connection setup |
| `exceptions.py` | Custom exception classes |
| `exception_handlers.py` | Global error handlers |
| `logging.py` | Structured logging configuration |

### `app/db/` - Database Layer

| File | Purpose |
|------|----------|
| `models.py` | SQLAlchemy model definitions |
| `database.py` | Session factory and dependency |
| `seeds.py` | Test data initialization |

**Key Models:**
- `CrawlSession` - Crawl session tracking
- `CrawlJob` - Individual crawl task
- `Page` - Indexed web page (PGroonga)
- `Site` - Domain information
- `ContentClassification` - Content type classification
- `QueryCluster` - Query grouping for NLP
- `IntentClassification` - Search intent classification

### `app/api/` - API Routes

| File | Purpose |
|------|----------|
| `crawler_router.py` | `/api/crawl/*` endpoints |
| `router.py` | Main router combining all routes |

**Crawler Endpoints:**
- `POST /api/crawl/start` - Initiate crawl session
- `POST /api/crawl/job/create` - Create crawl job
- `POST /api/crawl/job/auto` - Auto-crawl random sites ⭐ NEW
- `POST /api/crawl/job/status` - Update job status
- `POST /api/crawl/invalidate` - Clear domain cache
- `GET /api/crawl/stats` - Get crawl statistics

### `app/services/` - Business Logic

| File | Purpose |
|------|----------|
| `crawler.py` | Crawling service (orchestration) |

Orchestrates:
- Session creation
- Job management
- Cache invalidation

### `app/middleware/` - Request Processing

| File | Purpose |
|------|----------|
| `logging_middleware.py` | Request/response logging |
| `rate_limit_middleware.py` | Rate limiting enforcement |
| `request_id_middleware.py` | Request tracing |
| `security_headers_middleware.py` | Security headers |

### `alembic/versions/` - Database Schema Evolution

**Migration 001: Initial Schema**
```sql
CREATE TABLE crawl_sessions (...)
CREATE TABLE crawl_jobs (...)
CREATE TABLE page_analysis (...)
```

**Migration 002: Performance Indexes**
```sql
CREATE INDEX idx_crawl_jobs_session ON crawl_jobs(session_id)
CREATE INDEX idx_crawl_jobs_status ON crawl_jobs(status)
```

**Migration 003: Search Tables** ✨ NEW
```sql
CREATE TABLE sites (...)
CREATE TABLE pages WITH PGroonga FULL TEXT INDEX
CREATE TABLE content_classifications (...)
CREATE TABLE query_clusters (...)
CREATE TABLE intent_classifications (...)
```

## Data Flow

### Crawling Flow

```
1. User calls POST /api/crawl/job/auto
   ↓
2. crawler_router.auto_crawl() executed
   ↓
3. Queries existing CrawlSession records
   ↓
4. Randomly selects N domains
   ↓
5. For each domain:
   - Creates new CrawlSession
   - Creates CrawlJob for domain root
   - Returns job details
   ↓
6. External system processes CrawlJob:
   - Fetches pages
   - Extracts metadata
   - Stores in pages table
```

### Search Flow

```
1. User submits search query
   ↓
2. GET /search with query parameter
   ↓
3. search_router processes request
   ↓
4. PGroonga full-text search on pages table
   ↓
5. Ranking algorithm applies:
   - TF-IDF similarity
   - PageRank score
   - Click-through rate
   - Content freshness
   ↓
6. Results returned with click tracking ID
```

## Environment Configuration

See `.env.example` for all variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/transparent_search

# API
API_PORT=8080
API_HOST=0.0.0.0

# Crawler
CRAWLER_TIMEOUT=30
CRAWLER_MAX_DEPTH=5
CRAWLER_USER_AGENT=...
```

## Docker Compose Services

**docker-compose.yml** defines:

| Service | Image | Purpose |
|---------|-------|----------|
| `app` | Custom Dockerfile | FastAPI application |
| `db` | postgres:16 | PostgreSQL database |

Both services communicate via internal Docker network.

## Dependencies

See `requirements.txt`:

```
fastapi==0.109.0          # Web framework
sqlalchemy==2.0.23        # ORM
alembic==1.12.1           # Migrations
psycopg2-binary==2.9.9    # PostgreSQL driver
httpx==0.25.2             # Async HTTP client
beautifulsoup4==4.12.2    # HTML parsing
```

## Development Workflow

1. **Local Setup**
   ```bash
   docker-compose up --build
   ```

2. **Run Migrations**
   ```bash
   docker-compose exec app alembic upgrade head
   ```

3. **Verify API**
   ```bash
   curl http://localhost:8080/health
   ```

4. **Test Changes**
   ```bash
   docker-compose exec app pytest
   ```

5. **View Logs**
   ```bash
   docker-compose logs -f app
   ```

## Common Workflows

### Adding a New API Endpoint

1. Create handler in appropriate router file
2. Define request/response models
3. Add route decorator
4. Implement business logic
5. Add tests
6. Update README

### Creating a Database Migration

1. Modify `app/db/models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Edit migration file
4. Test migration: `alembic upgrade head`
5. Document changes in CHANGELOG

### Debugging Database Issues

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U postgres -d transparent_search

# Check table structure
\d pages

# View migration history
\dt alembic_version
```

---

For more information, see [README.md](../README.md) and [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md).
