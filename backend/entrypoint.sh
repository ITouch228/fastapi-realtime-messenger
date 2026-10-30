set -e

echo "Running migrations..."
alembic upgrade head

# dev (docker-compose.override.yml) ставит UVICORN_RELOAD=1 — hot reload.
# prod оставляет переменную unset — несколько воркеров, без reload.
if [ "${UVICORN_RELOAD:-0}" = "1" ]; then
    echo "Starting FastAPI (dev, --reload)..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi

echo "Starting FastAPI (prod)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-1}"
