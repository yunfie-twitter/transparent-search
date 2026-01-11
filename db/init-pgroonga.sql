-- Initialize PGroonga extension for full-text search
-- This script is automatically executed when the PostgreSQL container starts

-- Create PGroonga extension
CREATE EXTENSION IF NOT EXISTS pgroonga;

-- Verify PGroonga is installed
SELECT pgroonga_version();

-- Create index functions (if needed)
CREATE OR REPLACE FUNCTION pgroonga_validate_index_parameter(internal) RETURNS void AS 'pgroonga' LANGUAGE c;

COMMIT;
