-- PGroonga Extension
CREATE EXTENSION IF NOT EXISTS pgroonga;

-- 1. sites (New: Manage Domains & Favicons)
CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    domain TEXT UNIQUE NOT NULL,
    favicon_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. pages (Web Page Info)
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id), -- Linked to site
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    pagerank_score DOUBLE PRECISION DEFAULT 1.0,
    last_crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Full Text Search Index
CREATE INDEX IF NOT EXISTS pgroonga_content_index ON pages 
USING pgroonga (title, content);

-- 3. images (New: Link Images to Pages)
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    alt_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. links (Link Relationships for PageRank)
CREATE TABLE IF NOT EXISTS links (
    src_page_id INTEGER REFERENCES pages(id),
    dst_page_id INTEGER REFERENCES pages(id),
    PRIMARY KEY (src_page_id, dst_page_id)
);
