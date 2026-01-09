-- ============================================
-- Advanced Features: Trackers, Content Type, Intent
-- ============================================

-- 1. Tracker Detection
CREATE TABLE IF NOT EXISTS trackers (
    id SERIAL PRIMARY KEY,
    domain TEXT UNIQUE NOT NULL,
    name VARCHAR(100),
    category VARCHAR(50), -- 'analytics', 'advertising', 'heatmap', 'social', 'other'
    risk_level INT, -- 1 (minimal) ~ 5 (severe privacy risk)
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Page tracker relationships
CREATE TABLE IF NOT EXISTS page_trackers (
    id SERIAL PRIMARY KEY,
    page_id INT REFERENCES pages(id) ON DELETE CASCADE,
    tracker_id INT REFERENCES trackers(id),
    detection_method VARCHAR(50), -- 'script_src', 'img_pixel', 'beacon', 'iframe'
    first_detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(page_id, tracker_id)
);

-- Tracker risk score for pages
ALTER TABLE pages ADD COLUMN tracker_risk_score DOUBLE PRECISION DEFAULT 1.0; -- 1.0 = no trackers, <1.0 = risky

-- 2. Content Type Classification
CREATE TABLE IF NOT EXISTS content_classifications (
    id SERIAL PRIMARY KEY,
    page_id INT UNIQUE REFERENCES pages(id) ON DELETE CASCADE,
    
    -- Primary content type
    content_type VARCHAR(50), -- 'text_article', 'manga', 'video', 'image', 'forum', 'tool', 'unknown'
    type_confidence DOUBLE PRECISION, -- 0.0 ~ 1.0
    
    -- Text-specific metrics
    text_length INT,
    image_count INT,
    image_ratio DOUBLE PRECISION, -- 0.0 ~ 1.0
    has_video BOOLEAN,
    has_iframe BOOLEAN,
    avg_paragraph_length INT,
    
    -- Video-specific metrics
    video_duration_seconds INT,
    has_chapters BOOLEAN,
    has_subtitles BOOLEAN,
    
    -- Media-specific
    image_resolution_avg INT, -- approximate average resolution
    has_watermark BOOLEAN,
    
    -- Interaction & Quality
    has_table_of_contents BOOLEAN,
    has_interactive_elements BOOLEAN,
    js_size_bytes INT, -- JS payload size
    external_js_count INT,
    
    classified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Search Intent Classification
CREATE TABLE IF NOT EXISTS intent_classifications (
    id SERIAL PRIMARY KEY,
    query_cluster_id INT REFERENCES query_clusters(id) ON DELETE CASCADE,
    
    -- Intent type
    primary_intent VARCHAR(50), -- 'navigation', 'informational', 'transactional', 'question', 'research', 'debugging', 'product_research'
    intent_confidence DOUBLE PRECISION,
    
    -- Secondary intents
    secondary_intents VARCHAR(50)[] DEFAULT '{}',
    
    -- Learnings from user behavior
    avg_dwell_time_ms INT,
    avg_success_rate DOUBLE PRECISION,
    typical_user_expertise VARCHAR(50), -- 'beginner', 'intermediate', 'expert'
    is_time_sensitive BOOLEAN DEFAULT FALSE, -- e.g., "current events"
    is_location_relevant BOOLEAN DEFAULT FALSE,
    
    -- Quality indicators
    best_performing_content_type VARCHAR(50), -- which type users prefer for this intent
    common_keywords TEXT[],
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query_cluster_id)
);

-- Query intent mappings (rule-based)
CREATE TABLE IF NOT EXISTS intent_rules (
    id SERIAL PRIMARY KEY,
    pattern TEXT, -- regex or simple pattern
    intent_type VARCHAR(50),
    confidence DOUBLE PRECISION,
    rule_type VARCHAR(20), -- 'regex', 'exact', 'contains', 'startswith'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- Indexes for Performance
-- ============================================

CREATE INDEX trackers_domain_idx ON trackers(domain);
CREATE INDEX trackers_risk_idx ON trackers(risk_level DESC);
CREATE INDEX page_trackers_page_idx ON page_trackers(page_id);
CREATE INDEX page_trackers_risk_idx ON page_trackers(tracker_id);
CREATE INDEX content_classifications_type_idx ON content_classifications(content_type);
CREATE INDEX intent_classifications_intent_idx ON intent_classifications(primary_intent);

-- ============================================
-- Views
-- ============================================

-- View: Pages with tracker risk profile
CREATE OR REPLACE VIEW page_tracker_profile AS
SELECT
    p.id,
    p.url,
    p.title,
    COUNT(pt.id) as tracker_count,
    SUM(CASE WHEN t.risk_level >= 4 THEN 1 ELSE 0 END) as high_risk_tracker_count,
    STRING_AGG(DISTINCT t.category, ', ') as tracker_categories,
    p.tracker_risk_score,
    CASE
        WHEN COUNT(pt.id) = 0 THEN 'clean'
        WHEN SUM(CASE WHEN t.risk_level >= 4 THEN 1 ELSE 0 END) > 0 THEN 'risky'
        WHEN COUNT(pt.id) >= 5 THEN 'tracker_heavy'
        ELSE 'normal'
    END as tracker_profile
FROM pages p
LEFT JOIN page_trackers pt ON p.id = pt.page_id
LEFT JOIN trackers t ON pt.tracker_id = t.id
GROUP BY p.id, p.url, p.title, p.tracker_risk_score;

-- View: Content type distribution by search intent
CREATE OR REPLACE VIEW intent_content_preference AS
SELECT
    qc.canonical_query,
    ic.primary_intent,
    cc.content_type,
    COUNT(DISTINCT cc.page_id) as page_count,
    AVG(psm.success_rate) as avg_success_rate
FROM intent_classifications ic
JOIN query_clusters qc ON ic.query_cluster_id = qc.id
LEFT JOIN query_clusters qc_inner ON qc_inner.id = ic.query_cluster_id
LEFT JOIN pages p ON p.id = qc_inner.id -- This is simplified, needs proper join
LEFT JOIN content_classifications cc ON p.id = cc.page_id
LEFT JOIN page_success_matrix psm ON p.id = psm.page_id AND qc_inner.id = psm.query_cluster_id
GROUP BY qc.canonical_query, ic.primary_intent, cc.content_type
ORDER BY avg_success_rate DESC;
