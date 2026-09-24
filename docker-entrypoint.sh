#!/bin/sh
# Wait for the database, bring the schema up to date, then start serving.
#
# Migrations run here rather than by hand because a container that starts with
# an old schema fails in ways that look like application bugs. Running them on
# every start is safe: alembic does nothing when the database is already at
# head.

set -e

echo "waiting for the database…"

attempt=0
until python - <<'PY'
import os
import sys
import psycopg

url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")

try:
    with psycopg.connect(url, connect_timeout=3):
        pass
except Exception as exc:
    print(f"  not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PY
do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "database did not come up after 30 tries — giving up" >&2
        exit 1
    fi
    sleep 2
done

echo "database is up"

echo "applying migrations…"
flask db upgrade

echo "starting the application"
exec "$@"
