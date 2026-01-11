# Contributing Guide

Thank you for your interest in contributing to **Transparent Search**! This document provides guidelines for contributing to the project.

## Code of Conduct

This project adheres to the Contributor Covenant [Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/). By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- PostgreSQL 16 with PGroonga extension
- Git

### Local Development Setup

1. **Fork the repository**

```bash
git clone https://github.com/YOUR_USERNAME/transparent-search.git
cd transparent-search
```

2. **Create a feature branch**

```bash
git checkout -b feature/your-feature-name
```

3. **Set up environment**

```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Start Docker containers**

```bash
docker-compose up --build
```

5. **Run database migrations**

```bash
docker-compose exec app alembic upgrade head
```

6. **Verify installation**

```bash
curl http://localhost:8080/health
```

## Development Workflow

### Before Making Changes

1. Check the [Issues](https://github.com/yunfie-twitter/transparent-search/issues) page
2. Look for existing PRs to avoid duplicate work
3. For new features, open a discussion issue first
4. For bugs, include reproduction steps

### Making Changes

1. **Write clean, documented code**
   - Follow PEP 8 style guide
   - Use type hints
   - Add docstrings to functions and classes

2. **Keep commits atomic**
   - One logical change per commit
   - Use descriptive commit messages

3. **Update tests**
   - Add tests for new features
   - Ensure all tests pass

4. **Update documentation**
   - Update README if necessary
   - Add CHANGELOG entry
   - Update API docs if endpoints change

### Commit Message Format

Follow conventional commits:

```
type(scope): subject

body (optional)

footer (optional)
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style changes
- `refactor` - Refactoring
- `perf` - Performance improvements
- `test` - Test additions/changes
- `chore` - Build, CI/CD changes

**Examples:**
```
feat(crawler): add JavaScript rendering support
fix(search): resolve PGroonga ranking algorithm issue
docs(api): update endpoint documentation
```

## Project Structure

```
transparent-search/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── crawler_router.py      # Crawl API endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Configuration settings
│   │   ├── exceptions.py          # Custom exceptions
│   │   └── logging.py             # Logging setup
│   ├── db/
│   │   ├── __init__.py
│   │   └── models.py              # SQLAlchemy models
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── logging_middleware.py
│   │   └── rate_limit_middleware.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── search.py              # Search endpoints
│   │   ├── admin.py               # Admin endpoints
│   │   └── ...
│   └── services/
│       ├── __init__.py
│       └── crawler.py             # Crawler business logic
├── alembic/
│   ├── versions/
│   │   ├── 001_initial.py
│   │   ├── 002_indexes.py
│   │   └── 003_search_tables.py   # Latest migration
│   └── env.py
├── docs/
│   └── DATABASE_MIGRATION.md      # Migration guide
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── CHANGELOG.md
└── main.py                        # Entry point
```

## Key Files to Know

### `alembic/versions/`

Database migrations are stored here. Each file represents a schema change:
- `001_initial.py` - Initial crawl tables
- `002_indexes.py` - Performance indexes
- `003_search_tables.py` - Search-related tables with PGroonga

### `app/db/models.py`

SQLAlchemy model definitions:
- `CrawlSession` - Crawl session metadata
- `CrawlJob` - Individual crawl job
- `Page` - Web page content
- `Site` - Site information

### `app/api/crawler_router.py`

Crawl API endpoints:
- `POST /api/crawl/start` - Start crawl
- `POST /api/crawl/job/create` - Create job
- `POST /api/crawl/job/auto` - Auto crawl
- `POST /api/crawl/job/status` - Update job

## Testing

### Running Tests

```bash
# All tests
docker-compose exec app pytest

# Specific test file
docker-compose exec app pytest tests/test_crawler.py

# With coverage
docker-compose exec app pytest --cov=app
```

### Test Structure

```
tests/
├── test_crawler.py
├── test_api.py
├── test_database.py
└── conftest.py
```

## Database Migrations

### Creating a New Migration

```bash
# Generate migration skeleton
docker-compose exec app alembic revision --autogenerate -m "description"

# Edit the generated file in alembic/versions/
# Add upgrade() and downgrade() logic

# Apply migration
docker-compose exec app alembic upgrade head
```

### Migration Naming Convention

Format: `NNN_description.py`
- NNN = sequential number (001, 002, 003, ...)
- description = brief description (lowercase, underscores)

Examples:
- `003_add_search_tables.py`
- `004_add_intent_classification.py`

## Code Style

### Python

- **Formatter:** Follow PEP 8
- **Type Hints:** Always use type hints for function arguments and returns
- **Docstrings:** Use Google-style docstrings

Example:
```python
def create_crawl_job(
    session_id: str,
    domain: str,
    url: str,
    depth: int = 0,
    max_depth: int = 3,
) -> CrawlJob:
    """Create a new crawl job.
    
    Args:
        session_id: Associated crawl session ID
        domain: Target domain
        url: URL to crawl
        depth: Current crawl depth
        max_depth: Maximum crawl depth
        
    Returns:
        Created CrawlJob instance
        
    Raises:
        ValueError: If depth > max_depth
    """
    ...
```

### SQL

- Use uppercase for keywords (SELECT, INSERT, WHERE)
- Use lowercase for identifiers
- Use 4-space indentation for complex queries

## Pull Request Process

1. **Create a descriptive PR title**
   - Use same format as commit messages
   - Example: "feat(api): add auto-crawl endpoint"

2. **Fill out the PR template**
   - Describe changes
   - Link related issues
   - List breaking changes

3. **Ensure CI passes**
   - All tests pass
   - Code coverage maintained
   - No linting errors

4. **Request review**
   - At least one maintainer review required
   - Address review feedback

5. **Merge**
   - Use "Squash and merge" for single commits
   - Use "Create a merge commit" for feature branches

## Reporting Issues

### Bug Reports

Include:
- Python version
- PostgreSQL version
- PGroonga version
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case
- Proposed solution
- Alternative approaches considered
- Example API usage (if applicable)

## Documentation

### Updating README

- Keep it concise
- Update API documentation if endpoints change
- Include usage examples
- Link to detailed docs in `/docs/`

### Adding to Docs

Create markdown files in `/docs/` for:
- Architecture decisions
- Setup guides
- Migration information
- API specifications

## Performance Considerations

When contributing, keep in mind:

1. **Database Queries**
   - Minimize N+1 queries
   - Use appropriate indexes
   - Test with large datasets

2. **API Responses**
   - Keep response size reasonable
   - Implement pagination for lists
   - Use appropriate caching headers

3. **Crawler**
   - Respect robots.txt
   - Implement backoff strategies
   - Monitor memory usage

## Getting Help

- Check [Issues](https://github.com/yunfie-twitter/transparent-search/issues)
- Review [Discussion](https://github.com/yunfie-twitter/transparent-search/discussions)
- Read [Docs](docs/)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉
