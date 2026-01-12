-- PostgreSQL Initialization Script
-- This script will be run by the postgres user during container initialization

-- Create search_user role if it doesn't exist
DO $$ 
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'search_user') THEN
    CREATE ROLE search_user WITH LOGIN PASSWORD 'search_password';
    RAISE NOTICE 'Created role: search_user';
  ELSE
    RAISE NOTICE 'Role search_user already exists';
  END IF;
END $$;

-- Grant CREATEDB privilege to search_user
ALTER ROLE search_user CREATEDB;

-- Grant connection to search_user on postgres database
GRANT CONNECT ON DATABASE postgres TO search_user;

-- Grant privileges to search_user on transparent_search database
GRANT ALL PRIVILEGES ON DATABASE transparent_search TO search_user;
