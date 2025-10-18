#!/usr/bin/env bash
# Reset local storage (DB + vector store + caches).
# WARNING: This is destructive. Use on local/dev environments only.

set -euo pipefail

API="${API:-http://127.0.0.1:8000}"   # Not used directly; kept for symmetry with other scripts
DB_URL="${DATABASE_URL:-${DB_URL:-sqlite:///./app.db}}"
CHROMA_DIR="${CHROMA_PERSIST_DIR:-./var/chroma}"
UPLOAD_DIR="${UPLOAD_DIR:-./uploads}"
CACHE_DIR="${CACHE_DIR:-./.cache}"

echo "[reset] DB_URL=$DB_URL"
echo "[reset] CHROMA_DIR=$CHROMA_DIR"
echo "[reset] UPLOAD_DIR=$UPLOAD_DIR"
echo "[reset] CACHE_DIR=$CACHE_DIR"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing '$1' — please install it."; exit 1; }; }

case "$DB_URL" in
  sqlite:///*)
    # Examples:
    #   sqlite:///./app.db        (relative)
    #   sqlite:////abs/path.db    (absolute)
    DB_PATH="${DB_URL#sqlite:///}"
    echo "[reset] SQLite file: $DB_PATH"
    rm -f -- "$DB_PATH" "${DB_PATH}-wal" "${DB_PATH}-shm" "${DB_PATH}-journal" 2>/dev/null || true
    ;;
  postgresql://*|postgres://*)
    need psql
    echo "[reset] Resetting Postgres 'public' schema ..."
    # NOTE: Your DB user must have privileges to drop/create the 'public' schema.
    PSQL_URI="$DB_URL"
    PGPASSWORD='' psql "$PSQL_URI" -v ON_ERROR_STOP=1 -c 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;'
    ;;
  mysql://*|mariadb://*)
    need mysql
    echo "[reset] MySQL/MariaDB reset is environment-specific — handle manually if needed."
    echo "        e.g., mysql <db> -e 'DROP DATABASE <db>; CREATE DATABASE <db>;'"
    ;;
  *)
    echo "[reset] Unknown DB_URL scheme. Please reset your DB manually."
    ;;
esac

# Wipe Chroma (vector store)
if [ -d "$CHROMA_DIR" ]; then
  echo "[reset] rm -rf $CHROMA_DIR"
  rm -rf -- "$CHROMA_DIR"
fi

# Wipe uploads and cache (if present)
[ -d "$UPLOAD_DIR" ] && { echo "[reset] rm -rf $UPLOAD_DIR"; rm -rf -- "$UPLOAD_DIR"; }
[ -d "$CACHE_DIR" ]  && { echo "[reset] rm -rf $CACHE_DIR";  rm -rf -- "$CACHE_DIR"; }

# Common SQLite guesses (best-effort cleanup)
for guess in ./app.db ./data/app.db ./backend/app.db; do
  [ -f "$guess" ] && rm -f -- "$guess"
done

echo "[reset] done ✅"
