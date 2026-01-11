"""Initial migration: Create crawl management tables

Revision ID: 001
Revises: None
Create Date: 2026-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create crawl_sessions table
    op.create_table(
        'crawl_sessions',
        sa.Column('session_id', sa.String(36), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('total_pages', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('crawled_pages', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('failed_pages', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('session_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('session_id'),
        sa.Index('idx_domain_status', 'domain', 'status'),
        sa.Index('idx_created_at', 'created_at'),
    )

    # Create crawl_jobs table
    op.create_table(
        'crawl_jobs',
        sa.Column('job_id', sa.String(36), nullable=False),
        sa.Column('session_id', sa.String(36), nullable=True),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('url', sa.String(2048), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('depth', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_depth', sa.Integer(), nullable=True, server_default='3'),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('headings_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('internal_links_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('external_links_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('page_value_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('spam_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('relevance_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('has_structured_data', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('has_og_tags', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('has_meta_description', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('enable_js_rendering', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('crawled_pages', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('failed_pages', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('urls_to_crawl', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('job_id'),
        sa.ForeignKeyConstraint(['session_id'], ['crawl_sessions.session_id'], ),
        sa.Index('idx_domain_status', 'domain', 'status'),
        sa.Index('idx_created_at', 'created_at'),
        sa.Index('idx_page_value', 'page_value_score'),
        sa.Index('idx_spam_score', 'spam_score'),
        sa.Index('idx_priority_status', 'priority', 'status'),
    )

    # Create crawl_metadata table
    op.create_table(
        'crawl_metadata',
        sa.Column('metadata_id', sa.String(36), nullable=False),
        sa.Column('job_id', sa.String(36), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('og_title', sa.String(500), nullable=True),
        sa.Column('og_description', sa.Text(), nullable=True),
        sa.Column('og_image', sa.String(2048), nullable=True),
        sa.Column('og_type', sa.String(100), nullable=True),
        sa.Column('og_url', sa.String(2048), nullable=True),
        sa.Column('twitter_card', sa.String(100), nullable=True),
        sa.Column('twitter_title', sa.String(500), nullable=True),
        sa.Column('twitter_description', sa.Text(), nullable=True),
        sa.Column('twitter_image', sa.String(2048), nullable=True),
        sa.Column('structured_data', sa.JSON(), nullable=True),
        sa.Column('canonical_url', sa.String(2048), nullable=True),
        sa.Column('robots_directive', sa.String(255), nullable=True),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('charset', sa.String(50), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=True),
        sa.Column('modified_date', sa.DateTime(), nullable=True),
        sa.Column('author', sa.String(255), nullable=True),
        sa.Column('h1_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('h2_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('h3_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('images_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('images_with_alt', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('images_data', sa.JSON(), nullable=True),
        sa.Column('internal_links', sa.JSON(), nullable=True),
        sa.Column('external_links', sa.JSON(), nullable=True),
        sa.Column('extracted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('metadata_id'),
        sa.ForeignKeyConstraint(['job_id'], ['crawl_jobs.job_id'], ),
        sa.Index('idx_job_url', 'job_id', 'url'),
        sa.Index('idx_extracted_at', 'extracted_at'),
    )

    # Create page_analysis table
    op.create_table(
        'page_analysis',
        sa.Column('analysis_id', sa.String(36), nullable=False),
        sa.Column('job_id', sa.String(36), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('depth_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('link_popularity_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('content_quality_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('metadata_completeness_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('freshness_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('uniqueness_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('total_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('crawl_priority', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('recommendation', sa.String(50), nullable=True),
        sa.Column('link_farm_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('reciprocal_linking_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('content_duplication_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('cms_anomaly_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('ip_reputation_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('spam_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('risk_level', sa.String(50), nullable=True),
        sa.Column('spam_signals', sa.JSON(), nullable=True),
        sa.Column('query_intent', sa.String(50), nullable=True),
        sa.Column('intent_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('page_type', sa.String(100), nullable=True),
        sa.Column('relevance_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('intent_match_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('content_match_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('analyzed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('analysis_id'),
        sa.ForeignKeyConstraint(['job_id'], ['crawl_jobs.job_id'], ),
        sa.Index('idx_job_url', 'job_id', 'url'),
        sa.Index('idx_total_score', 'total_score'),
        sa.Index('idx_spam_score', 'spam_score'),
        sa.Index('idx_relevance', 'relevance_score'),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('page_analysis')
    op.drop_table('crawl_metadata')
    op.drop_table('crawl_jobs')
    op.drop_table('crawl_sessions')
