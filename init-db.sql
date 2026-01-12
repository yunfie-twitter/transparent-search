-- PostgreSQL Initialization Script
-- This script will be run by the postgres user during container initialization
-- It safely handles both fresh installations and existing databases

-- Terminate existing connections from search_user
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'search_user' AND pid <> pg_backend_pid();

-- Drop existing search_user if it exists (to handle re-initialization)
DO $$ 
BEGIN
  IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'search_user') THEN
    REASSIGN OWNED BY search_user TO postgres;
    DROP OWNED BY search_user;
    DROP ROLE search_user;
  END IF;
END $$;

-- Create fresh search_user role
CREATE ROLE search_user WITH LOGIN PASSWORD 'search_password' CREATEDB;

-- Ensure transparent_search database exists
DO $$ 
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'transparent_search') THEN
    EXECUTE 'CREATE DATABASE transparent_search OWNER search_user';
  ELSE
    -- Change owner to search_user if not already
    EXECUTE 'ALTER DATABASE transparent_search OWNER TO search_user';
  END IF;
END $$;

-- Grant basic privileges
GRANT CONNECT ON DATABASE postgres TO search_user;
GRANT ALL PRIVILEGES ON DATABASE transparent_search TO search_user;

-- Connect to transparent_search and set up schema
\c transparent_search search_user

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
