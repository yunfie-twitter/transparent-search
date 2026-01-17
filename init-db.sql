-- PostgreSQL Initialization Script
-- This script will be run by the postgres user during container initialization
-- It safely handles both fresh installations and existing databases

-- Set client encoding
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- Terminate existing connections from search_user
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'search_user' AND pid <> pg_backend_pid();

-- Drop existing search_user if it exists (to handle re-initialization)
DO $$ 
BEGIN
  IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'search_user') THEN
    REASSIGN OWNED BY search_user TO postgres;
    DROP OWNED BY search_user CASCADE;
    DROP ROLE search_user;
  END IF;
END $$;

-- Drop transparent_search database if exists for clean state
DO $$ 
BEGIN
  EXECUTE 'DROP DATABASE IF EXISTS transparent_search';
END $$;

-- Create fresh search_user role
CREATE ROLE search_user WITH LOGIN PASSWORD 'search_password' CREATEDB CREATEROLE INHERIT;

-- Create transparent_search database with proper settings
CREATE DATABASE transparent_search
  OWNER search_user
  TEMPLATE template0
  ENCODING 'UTF8'
  LC_COLLATE 'en_US.UTF-8'
  LC_CTYPE 'en_US.UTF-8';

-- Grant full privileges to search_user
GRANT ALL PRIVILEGES ON DATABASE transparent_search TO search_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO search_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO search_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO search_user;

-- Grant minimal privileges to public
GRANT CONNECT ON DATABASE transparent_search TO PUBLIC;

COMMIT;
