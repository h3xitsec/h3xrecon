#!/bin/bash
set -e

# Create required directories with proper permissions
#mkdir -p /etc/pgbouncer
#chmod 755 /etc/pgbouncer

# Connect to PostgreSQL to get the SCRAM-SHA-256 password
PGPASSWORD="${POSTGRESQL_PASSWORD}" psql "host=${POSTGRESQL_HOST} port=${POSTGRESQL_PORT} dbname=${POSTGRESQL_DATABASE} user=${POSTGRESQL_USER}" -t -c "SELECT concat('\"', usename, '\" \"', passwd, '\"') FROM pg_shadow WHERE usename = '${POSTGRESQL_USER}';" > /etc/pgbouncer/userlist.txt

#chmod 644 /etc/pgbouncer/userlist.txt

# Start PgBouncer
exec pgbouncer /etc/pgbouncer/pgbouncer.ini