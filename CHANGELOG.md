# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ✨ **Auto-crawl endpoint** (`POST /api/crawl/job/auto`)
  - Automatically start crawl jobs for random registered sites
  - Support for `max_jobs` and `max_depth` parameters
  - Enables continuous crawling workflow without manual intervention
  - See [README Section 5](README.md#5-api仕様-fastapi) for usage details

- 📊 **Database Migration 003: Search Tables**
  - Added `sites` table for site management
  - Added `pages` table with PGroonga full-text search support
  - Added `content_classifications` table for content type detection
  - Added `query_clusters` table for query clustering
  - Added `intent_classifications` table for search intent classification
  - See [docs/DATABASE_MIGRATION.md](docs/DATABASE_MIGRATION.md) for details

### Fixed

- 🔧 **Router reference in main.py**
  - Changed `router.router` to `router` in `app.include_router()` calls
  - Resolved `AttributeError: module 'app.api.router' has no attribute 'router'`

- 📝 **Database schema alignment**
  - Resolved `UndefinedTableError: relation "pages" does not exist`
  - All search API endpoints now have required database tables

### Documentation

- 📖 Updated README with comprehensive API documentation
- 📚 Created `docs/DATABASE_MIGRATION.md` with migration guide
- 🚀 Added setup and execution instructions
- 🐛 Added troubleshooting section

## [0.1.0] - 2026-01-11

### Initial Release

#### Features

- 🔍 **FastAPI-based search engine**
  - Zero-ETL architecture using PostgreSQL only
  - PGroonga integration for Japanese full-text search
  - Advanced ranking algorithm with TF-IDF, PageRank, and click signals

- 🕷️ **Asynchronous web crawler**
  - Support for multiple async engines (VOCALOID, SynthV, CeVIO, UTAU)
  - robots.txt compliance
  - Sitemap parsing
  - OGP and JSON-LD extraction

- 📦 **Database schema**
  - sites: Domain management
  - pages: Web page content with PGroonga indexing
  - images: Extracted image metadata
  - search_queries: Search logging
  - clicks: Click-through learning

- 🔌 **Core API endpoints**
  - `POST /api/crawl/start` - Start crawl session
  - `POST /api/crawl/job/create` - Create crawl job
  - `POST /api/crawl/job/status` - Update job status
  - `POST /api/crawl/invalidate` - Invalidate domain cache
  - `GET /api/crawl/stats` - Get crawl statistics

- 🚢 **Docker deployment**
  - Docker Compose setup with PostgreSQL + PGroonga
  - Automated database migrations using Alembic
  - Health checks and logging middleware

#### Technology Stack

- **Language:** Python 3.12+
- **Web Framework:** FastAPI
- **Database:** PostgreSQL 16 + PGroonga
- **Crawler:** httpx + BeautifulSoup4
- **Migration:** Alembic
- **Container:** Docker & Docker Compose

#### Known Issues

- PGroonga requires PostgreSQL 16+ with PGroonga extension installed
- JavaScript rendering disabled by default (for performance)
- Rate limiting middleware not yet integrated

---

## Migrations Implemented

### 001_initial_migration
- Create initial crawl session and job tables
- Create metadata and analysis tables

### 002_add_performance_indexes
- Add composite indexes for query optimization
- Add partial indexes for active jobs
- Add GIN indexes for JSONB columns

### 003_add_search_tables
- Add `sites` table
- Add `pages` table with PGroonga indexing
- Add `content_classifications` table
- Add `query_clusters` table
- Add `intent_classifications` table

---

## Future Roadmap

- [ ] JavaScript rendering support with Playwright
- [ ] Advanced rate limiting and backoff strategies
- [ ] Real-time indexing pipeline
- [ ] Query suggestion improvements
- [ ] Analytics dashboard
- [ ] Multi-language support beyond Japanese
- [ ] Mobile app for crawl monitoring
- [ ] REST API rate limiting tiers
- [ ] WebSocket support for real-time updates
- [ ] ML-based ranking optimization

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License - see LICENSE file for details

---

## Contact

[@yunfie-twitter](https://github.com/yunfie-twitter)
