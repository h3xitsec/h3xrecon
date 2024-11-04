FROM postgres
ENV POSTGRES_DB=h3xrecon
ENV POSTGRES_PASSWORD_FILE=/run/secrets/postgresql_db_password
ENV POSTGRES_USER=h3xrecon
COPY ./psql_dump.sql /docker-entrypoint-initdb.d/
