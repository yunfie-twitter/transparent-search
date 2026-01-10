"""Add performance optimization indexes

Revision ID: 002
Revises: 001
Create Date: 2026-01-10

Adds composite indexes, partial indexes, and query optimization for:
- Domain + Status + Priority queries
- Score-based sorting
- Time range queries
- Spam detection

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for main crawl query
    op.create_index(
        'idx_crawl_jobs_domain_status_priority',
        'crawl_jobs',
        ['domain', 'status', 'priority', 'page_value_score'],
        unique=False
    )
    
    # Composite index for score-based queries
    op.create_index(
        'idx_crawl_jobs_scores',
        'crawl_jobs',
        ['page_value_score', 'spam_score', 'relevance_score'],
        unique=False
    )
    
    # Partial index for pending jobs (faster filtering)
    op.create_index(
        'idx_crawl_jobs_pending',
        'crawl_jobs',
        ['domain', 'priority', 'created_at'],
        postgresql_where=sa.text("status = 'pending'"),
        unique=False
    )
    
    # Partial index for active sessions
    op.create_index(
        'idx_crawl_sessions_active',
        'crawl_sessions',
        ['domain', 'created_at'],
        postgresql_where=sa.text("status != 'completed'"),
        unique=False
    )
    
    # Composite index for metadata extraction
    op.create_index(
        'idx_crawl_metadata_job_extracted',
        'crawl_metadata',
        ['job_id', 'extracted_at'],
        unique=False
    )
    
    # Composite index for analysis scoring
    op.create_index(
        'idx_page_analysis_scores',
        'page_analysis',
        ['job_id', 'total_score', 'spam_score', 'relevance_score'],
        unique=False
    )
    
    # Partial index for spam detection
    op.create_index(
        'idx_page_analysis_spam',
        'page_analysis',
        ['url', 'spam_score'],
        postgresql_where=sa.text("spam_score > 70"),
        unique=False
    )
    
    # Partial index for high-value pages
    op.create_index(
        'idx_crawl_jobs_high_value',
        'crawl_jobs',
        ['domain', 'page_value_score', 'created_at'],
        postgresql_where=sa.text("page_value_score >= 75"),
        unique=False
    )
    
    # Time range queries optimization
    op.create_index(
        'idx_crawl_jobs_dates',
        'crawl_jobs',
        ['created_at', 'completed_at'],
        unique=False
    )
    
    op.create_index(
        'idx_page_analysis_dates',
        'page_analysis',
        ['analyzed_at'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes in reverse order
    op.drop_index('idx_page_analysis_dates', table_name='page_analysis')
    op.drop_index('idx_crawl_jobs_dates', table_name='crawl_jobs')
    op.drop_index('idx_crawl_jobs_high_value', table_name='crawl_jobs')
    op.drop_index('idx_page_analysis_spam', table_name='page_analysis')
    op.drop_index('idx_page_analysis_scores', table_name='page_analysis')
    op.drop_index('idx_crawl_metadata_job_extracted', table_name='crawl_metadata')
    op.drop_index('idx_crawl_sessions_active', table_name='crawl_sessions')
    op.drop_index('idx_crawl_jobs_pending', table_name='crawl_jobs')
    op.drop_index('idx_crawl_jobs_scores', table_name='crawl_jobs')
    op.drop_index('idx_crawl_jobs_domain_status_priority', table_name='crawl_jobs')
