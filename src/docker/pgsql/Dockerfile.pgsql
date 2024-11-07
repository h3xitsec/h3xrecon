FROM postgres

COPY h3xrecon/psql_dump.sql /docker-entrypoint-initdb.d/