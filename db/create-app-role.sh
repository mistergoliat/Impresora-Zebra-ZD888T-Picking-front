#!/usr/bin/env bash
set -euo pipefail

APP_ROLE_NAME="${APP_ROLE_NAME:-app}"
APP_ROLE_PASSWORD="${APP_ROLE_PASSWORD:-${PGPASSWORD:-${POSTGRES_PASSWORD:-}}}"
APP_ROLE_PASSWORD="${APP_ROLE_PASSWORD:-${PGPASSWORD:-}}"
APP_DATABASE="${APP_DATABASE:-${POSTGRES_DB:-picking}}"
APP_ROLE_SET_OWNER="${APP_ROLE_SET_OWNER:-true}"
DB_FOR_CONNECTION="${POSTGRES_DB:-postgres}"

if [[ -z "${APP_ROLE_PASSWORD}" ]]; then
  echo "[create-app-role] APP_ROLE_PASSWORD or PGPASSWORD must be provided" >&2
  exit 1
fi

psql \
  -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${DB_FOR_CONNECTION}" \
  -v app_role="${APP_ROLE_NAME}" \
  -v app_password="${APP_ROLE_PASSWORD}" \
  -v app_database="${APP_DATABASE}" \
  -v app_set_owner="${APP_ROLE_SET_OWNER}" <<'EOSQL'
DO
$$
DECLARE
    role_name text := :'app_role';
    role_password text := :'app_password';
    database_name text := :'app_database';
    should_set_owner boolean := :'app_set_owner'::boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
        EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', role_name, role_password);
    ELSE
        EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', role_name, role_password);
    END IF;

    IF should_set_owner THEN
        EXECUTE format('ALTER DATABASE %I OWNER TO %I', database_name, role_name);
    END IF;

    EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', database_name, role_name);
END
$$;
EOSQL
