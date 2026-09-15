#!/usr/bin/env bash
# Runs once, automatically, the first time the postgres data volume is
# created (official postgres image behavior for /docker-entrypoint-initdb.d).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE ${AIRFLOW_DB_NAME}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AIRFLOW_DB_NAME}')\gexec

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${AIRFLOW_DB_USER}') THEN
            CREATE ROLE ${AIRFLOW_DB_USER} LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
        END IF;
    END
    \$\$;
    GRANT ALL PRIVILEGES ON DATABASE ${AIRFLOW_DB_NAME} TO ${AIRFLOW_DB_USER};

    SELECT 'CREATE DATABASE ${ANALYTICS_DB_NAME}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${ANALYTICS_DB_NAME}')\gexec

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${ANALYTICS_RO_USER}') THEN
            CREATE ROLE ${ANALYTICS_RO_USER} LOGIN PASSWORD '${ANALYTICS_RO_PASSWORD}';
        END IF;
    END
    \$\$;
    GRANT CONNECT ON DATABASE ${ANALYTICS_DB_NAME} TO ${ANALYTICS_RO_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AIRFLOW_DB_NAME" <<-EOSQL
    GRANT ALL ON SCHEMA public TO ${AIRFLOW_DB_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ANALYTICS_DB_NAME" <<-EOSQL
    CREATE SCHEMA IF NOT EXISTS fraud_pattern AUTHORIZATION ${POSTGRES_USER};
    GRANT USAGE ON SCHEMA fraud_pattern TO ${ANALYTICS_RO_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA fraud_pattern GRANT SELECT ON TABLES TO ${ANALYTICS_RO_USER};
EOSQL
