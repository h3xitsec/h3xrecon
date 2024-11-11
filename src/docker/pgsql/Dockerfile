FROM postgres

# Create migrations directory
RUN mkdir -p /migrations

# Copy all migration files
COPY migrations/*.sql /migrations/

# Copy the migration script
COPY migrate.sh /migrate.sh
RUN chmod +x /migrate.sh