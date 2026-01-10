-- Extensions
CREATE EXTENSION IF NOT EXISTS pgroonga;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. sites (Domains & Favicons)
CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    domain TEXT UNIQUE NOT NULL,
    favicon_url TEXT,
    robots_txt_url TEXT,
    sitemap_url TEXT,
    trust_score DOUBLE PRECISION DEFAULT 1.0, -- Added: Domain Trust Rank
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. pages (Web Page Info)
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id),
    url TEXT UNIQUE NOT NULL,

    title TEXT,
    h1 TEXT,
    content TEXT,

    -- Structured data (OGP / JSON-LD)
    og_title TEXT,
    og_description TEXT,
    og_image_url TEXT,
    jsonld JSONB,

    -- Ranking features
    pagerank_score DOUBLE PRECISION DEFAULT 1.0,
    click_score DOUBLE PRECISION DEFAULT 0.0,
    tracker_risk_score DOUBLE PRECISION DEFAULT 1.0,

    last_crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Search indexes
CREATE INDEX IF NOT EXISTS pgroonga_content_index ON pages USING pgroonga (title, h1, content);
CREATE INDEX IF NOT EXISTS pages_title_trgm_idx ON pages USING gin (title gin_trgm_ops);

-- 3. images (Link Images to Pages)
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    alt_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pgroonga_images_index ON images USING pgroonga (alt_text); -- Added for Image Search

-- 4. links (Link Relationships for PageRank)
CREATE TABLE IF NOT EXISTS links (
    src_page_id INTEGER REFERENCES pages(id),
    dst_page_id INTEGER REFERENCES pages(id),
    PRIMARY KEY (src_page_id, dst_page_id)
);

-- 5. search_queries (Query log for analytics + click learning)
CREATE TABLE IF NOT EXISTS search_queries (
    id BIGSERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    took_ms INTEGER,
    results_count INTEGER
);

-- Add index for autocomplete on queries
CREATE INDEX IF NOT EXISTS search_queries_query_trgm_idx ON search_queries USING gin (query gin_trgm_ops);

-- 6. clicks (Click log)
CREATE TABLE IF NOT EXISTS clicks (
    id BIGSERIAL PRIMARY KEY,
    query_id BIGINT REFERENCES search_queries(id) ON DELETE CASCADE,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. content_classifications (Content Type Classification)
CREATE TABLE IF NOT EXISTS content_classifications (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    content_type VARCHAR(50),
    type_confidence DOUBLE PRECISION DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(page_id)
);
CREATE INDEX IF NOT EXISTS content_classifications_page_id_idx ON content_classifications(page_id);

-- 8. query_clusters (Query Clustering for Intent)
CREATE TABLE IF NOT EXISTS query_clusters (
    id SERIAL PRIMARY KEY,
    query_text VARCHAR(500),
    cluster_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS query_clusters_hash_idx ON query_clusters(cluster_hash);

-- 9. intent_classifications (Query Intent Classification)
CREATE TABLE IF NOT EXISTS intent_classifications (
    id SERIAL PRIMARY KEY,
    query_cluster_id INTEGER REFERENCES query_clusters(id) ON DELETE CASCADE,
    primary_intent VARCHAR(50),
    intent_confidence DOUBLE PRECISION DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query_cluster_id)
);
CREATE INDEX IF NOT EXISTS intent_classifications_cluster_id_idx ON intent_classifications(query_cluster_id);
