#!/bin/bash
# Initialize PGroonga extension in PostgreSQL

set -e

echo "🔧 Initializing PGroonga extension..."

# Wait for PostgreSQL to be ready
until pg_isready -h localhost -U postgres; do
  echo '⏳ Waiting for PostgreSQL...'
  sleep 1
done

echo "✅ PostgreSQL is ready"

# Create PGroonga extension
echo "📦 Creating PGroonga extension..."
psql -U postgres -d transparent_search <<EOF
  CREATE EXTENSION IF NOT EXISTS pgroonga;
  SELECT pgroonga_version();
EOF

echo "✅ PGroonga initialized successfully"
