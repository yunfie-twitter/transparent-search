-- PGroonga Extension
CREATE EXTENSION IF NOT EXISTS pgroonga;

-- 1. pages (Web Page Info)
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    pagerank_score DOUBLE PRECISION DEFAULT 1.0,
    last_crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Full Text Search Index
CREATE INDEX IF NOT EXISTS pgroonga_content_index ON pages 
USING pgroonga (title, content);

-- 2. links (Link Relationships for PageRank)
CREATE TABLE IF NOT EXISTS links (
    src_page_id INTEGER REFERENCES pages(id),
    dst_page_id INTEGER REFERENCES pages(id),
    PRIMARY KEY (src_page_id, dst_page_id)
);
