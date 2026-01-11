"""Add search-specific tables for advanced search functionality

Revision ID: 003
Revises: 002
Create Date: 2026-01-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sites table
    op.create_table(
        'sites',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False, unique=True),
        sa.Column('favicon_url', sa.String(2048), nullable=True),
        sa.Column('trust_score', sa.Float(), nullable=True, server_default='0.5'),
        sa.Column('last_crawled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_sites_domain', 'domain'),
    )

    # Create pages table with PGroonga full-text search support
    op.create_table(
        'pages',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('site_id', sa.String(36), nullable=True),
        sa.Column('url', sa.String(2048), nullable=False, unique=True),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('h1', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('og_title', sa.String(500), nullable=True),
        sa.Column('og_description', sa.Text(), nullable=True),
        sa.Column('og_image_url', sa.String(2048), nullable=True),
        sa.Column('last_crawled_at', sa.DateTime(), nullable=True),
        sa.Column('tracker_risk_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('pagerank_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('click_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ),
        sa.Index('idx_pages_url', 'url'),
        sa.Index('idx_pages_site_id', 'site_id'),
        sa.Index('idx_pages_last_crawled', 'last_crawled_at'),
    )

    # Create content_classifications table
    op.create_table(
        'content_classifications',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('page_id', sa.String(36), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('type_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
        sa.Index('idx_content_classifications_page_id', 'page_id'),
        sa.Index('idx_content_classifications_content_type', 'content_type'),
    )

    # Create query_clusters table
    op.create_table(
        'query_clusters',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('query', sa.String(500), nullable=True),
        sa.Column('cluster_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_query_clusters_query', 'query'),
    )

    # Create intent_classifications table
    op.create_table(
        'intent_classifications',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('query_cluster_id', sa.String(36), nullable=False),
        sa.Column('primary_intent', sa.String(50), nullable=True),
        sa.Column('intent_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['query_cluster_id'], ['query_clusters.id'], ),
        sa.Index('idx_intent_classifications_query_cluster_id', 'query_cluster_id'),
        sa.Index('idx_intent_classifications_primary_intent', 'primary_intent'),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('intent_classifications')
    op.drop_table('query_clusters')
    op.drop_table('content_classifications')
    op.drop_table('pages')
    op.drop_table('sites')
