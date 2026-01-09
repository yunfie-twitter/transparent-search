-- ============================================
-- Collective Intelligence Score Schema
-- ============================================

-- 1. Sessions (User session tracking)
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    session_hash TEXT UNIQUE NOT NULL, -- SHA256(IP + UA + cookie?) for privacy
    ip_hash TEXT NOT NULL,             -- Hashed IP for anomaly detection
    user_agent_hash TEXT NOT NULL,     -- Hashed UA
    first_search_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- User Trust Score (long-term usage signal)
    days_active INT DEFAULT 0,          -- Cumulative days of activity
    total_searches INT DEFAULT 0,       -- Total searches from this session
    avg_time_between_searches INTERVAL, -- Behavioral signal
    trust_score DOUBLE PRECISION DEFAULT 0.5, -- 0.0 (bot-like) ~ 1.0+ (trusted long-term user)
    
    is_anomalous BOOLEAN DEFAULT FALSE  -- Anomaly detection flag
);
CREATE INDEX sessions_ip_hash_idx ON sessions(ip_hash);
CREATE INDEX sessions_last_activity_idx ON sessions(last_activity_at DESC);

-- 2. Search Events (Queries)
CREATE TABLE IF NOT EXISTS search_events (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(id) ON DELETE CASCADE,
    
    query TEXT NOT NULL,
    original_query TEXT,  -- Before normalization
    normalized_query TEXT, -- After normalization (aliases/abbreviations)
    query_cluster_id INT,  -- Grouping ID for variants (e.g., "python" cluster)
    
    -- Intent classification
    intent_type VARCHAR(20), -- 'explain', 'howto', 'debug', 'reference', 'product_research', etc.
    intent_confidence DOUBLE PRECISION, -- 0.0 ~ 1.0
    
    -- Result presentation
    results_count INT,
    took_ms INT,
    
    -- Session context
    time_since_last_search INT,  -- seconds (NULL if first in session)
    search_number_in_session INT, -- 1st, 2nd, 3rd search...
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX search_events_session_idx ON search_events(session_id);
CREATE INDEX search_events_query_cluster_idx ON search_events(query_cluster_id);
CREATE INDEX search_events_created_idx ON search_events(created_at DESC);

-- 3. Click Events (Detailed clicks)
CREATE TABLE IF NOT EXISTS click_events (
    id BIGSERIAL PRIMARY KEY,
    search_event_id BIGINT REFERENCES search_events(id) ON DELETE CASCADE,
    page_id INT REFERENCES pages(id) ON DELETE CASCADE,
    
    -- Click details
    rank_position INT NOT NULL,  -- Position in SERP (1st, 2nd, etc.)
    time_to_click_ms INT,       -- Time from search results to click
    clicked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Page interaction after click
    time_on_page_ms INT,        -- How long user stayed on page
    scroll_depth DOUBLE PRECISION, -- 0.0 ~ 1.0 (fraction of page scrolled)
    interaction_signals TEXT,   -- JSON: {"copied": true, "expanded": 3, ...}
    
    -- Success signal
    is_success_signal BOOLEAN DEFAULT FALSE, -- True if: long stay + no re-search
    success_reason VARCHAR(50),  -- 'long_stay', 'shared', 'bookmarked', etc.
    
    -- Session continuation
    next_search_time_ms INT,     -- Time to next search (NULL = last in session)
    is_terminal_click BOOLEAN DEFAULT FALSE -- No more searches after this
);
CREATE INDEX click_events_search_event_idx ON click_events(search_event_id);
CREATE INDEX click_events_page_idx ON click_events(page_id);
CREATE INDEX click_events_success_idx ON click_events(is_success_signal);
CREATE INDEX click_events_clicked_idx ON click_events(clicked_at DESC);

-- 4. Page Success Matrix (Core for ranking)
CREATE TABLE IF NOT EXISTS page_success_matrix (
    id SERIAL PRIMARY KEY,
    query_cluster_id INT NOT NULL, -- e.g., "python for loop" cluster
    page_id INT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    
    -- Core metrics
    impressions INT DEFAULT 0,        -- How many times this page was in SERP for this query
    success_events INT DEFAULT 0,     -- How many times it led to "success"
    click_count INT DEFAULT 0,        -- Raw clicks (including failed ones)
    
    -- Success rate (core metric for ranking)
    success_rate DOUBLE PRECISION GENERATED ALWAYS AS (
        CASE WHEN impressions > 0 
             THEN LEAST(1.0, success_events::DOUBLE PRECISION / impressions)
             ELSE 0.0
        END
    ) STORED,
    
    -- Temporal metrics
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Time decay weight
    time_decay_factor DOUBLE PRECISION DEFAULT 1.0, -- exp(-λ * days_old)
    
    -- Weighted score (success_rate * time_decay * quality_factor)
    collective_intelligence_score DOUBLE PRECISION GENERATED ALWAYS AS (
        success_rate * time_decay_factor
    ) STORED,
    
    UNIQUE(query_cluster_id, page_id)
);
CREATE INDEX matrix_query_cluster_idx ON page_success_matrix(query_cluster_id);
CREATE INDEX matrix_page_idx ON page_success_matrix(page_id);
CREATE INDEX matrix_score_idx ON page_success_matrix(collective_intelligence_score DESC);

-- 5. Anomaly Detection Log
CREATE TABLE IF NOT EXISTS anomaly_detections (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(id),
    anomaly_type VARCHAR(50), -- 'click_spike', 'rapid_pattern', 'ip_spam', etc.
    description TEXT,
    severity INT, -- 1 (light) ~ 5 (severe bot)
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    action_taken VARCHAR(50)  -- 'weight_reduced', 'blocked_temp', 'flagged'
);

-- 6. Query Clusters (Normalization groups)
CREATE TABLE IF NOT EXISTS query_clusters (
    id SERIAL PRIMARY KEY,
    canonical_query TEXT UNIQUE NOT NULL, -- Main representative
    aliases TEXT[] DEFAULT '{}',          -- Variations ["Python for", "pythonfor", "パイソン for"]
    intent_type VARCHAR(20),              -- Shared intent
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX query_clusters_aliases_idx ON query_clusters USING gin(aliases);

-- ============================================
-- Utility Views
-- ============================================

-- View: Recent Success Rate (with time decay applied)
CREATE OR REPLACE VIEW page_success_ranking AS
SELECT 
    qc.id as query_cluster_id,
    qc.canonical_query,
    p.id as page_id,
    p.title,
    p.url,
    psm.impressions,
    psm.success_events,
    psm.success_rate,
    psm.time_decay_factor,
    psm.collective_intelligence_score,
    -- Recency weight
    GREATEST(0.1, EXP(-0.1 * EXTRACT(DAY FROM NOW() - psm.last_updated_at))) as recency_weight
FROM page_success_matrix psm
JOIN query_clusters qc ON psm.query_cluster_id = qc.id
JOIN pages p ON psm.page_id = p.id
WHERE psm.impressions >= 5 -- Minimum impressions threshold
ORDER BY psm.collective_intelligence_score DESC;

-- View: User Trust Scores
CREATE OR REPLACE VIEW user_trust_scores AS
SELECT 
    id,
    session_hash,
    days_active,
    total_searches,
    trust_score,
    is_anomalous,
    CASE 
        WHEN trust_score >= 0.8 THEN 'trusted_long_term'
        WHEN trust_score >= 0.5 AND days_active >= 7 THEN 'established'
        WHEN trust_score >= 0.3 AND is_anomalous = false THEN 'normal'
        WHEN is_anomalous = true THEN 'suspicious'
        ELSE 'new'
    END as user_category
FROM sessions
WHERE last_activity_at > NOW() - INTERVAL '90 days';
