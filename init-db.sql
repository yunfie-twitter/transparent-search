-- Create search_user role if it doesn't exist
CREATE ROLE search_user WITH LOGIN PASSWORD 'search_password';

-- Grant privileges
ALTER ROLE search_user CREATEDB;

-- Create database if it doesn't exist
CREATE DATABASE transparent_search OWNER search_user;

-- Grant all privileges on the database
GRANT ALL PRIVILEGES ON DATABASE transparent_search TO search_user;
