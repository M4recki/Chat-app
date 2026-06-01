#!/bin/sh
set -e

echo "Waiting for database to become available..."
python - <<'PY'
import os, time
from sqlalchemy import create_engine

url = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/chatapp')
for _ in range(60):
    try:
        create_engine(url).connect().close()
        print('Database reachable')
        break
    except Exception as e:
        print('Database not ready, retrying...', e)
        time.sleep(1)
else:
    raise SystemExit('Database not ready after timeout')
PY

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
