#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    echo "Waiting for PostgreSQL to be ready..."
    sleep 2
done

# Create migrations table if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
EOSQL

# Get list of migration files
cd /migrations
migrations=(*.sql)

# Sort migrations numerically
IFS=$'\n' sorted=($(sort -n <<<"${migrations[*]}"))
unset IFS

# Apply each migration in order
for migration in "${sorted[@]}"; do
    version=$(echo $migration | cut -d'_' -f1)
    
    # Check if migration has been applied
    if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
        "SELECT 1 FROM schema_migrations WHERE version = $version" | grep -q 1; then
        
        echo "Applying migration $migration..."
        
        # Start transaction
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
            BEGIN;
            \i /migrations/$migration
            INSERT INTO schema_migrations (version) VALUES ($version);
            COMMIT;
EOSQL
        
        echo "Migration $migration applied successfully"
    else
        echo "Migration $migration already applied"
    fi
done