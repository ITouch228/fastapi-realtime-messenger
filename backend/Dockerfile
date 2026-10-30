# syntax=docker/dockerfile:1
FROM python:3.12

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl нужен для HEALTHCHECK; python:3.12 (full) уже содержит sh
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Зависимости ставим до копирования кода — слой кешируется
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Секреты (.env, keys/) и мусор исключены через .dockerignore
COPY . .

# Непривилегированный пользователь + каталоги, в которые пишет приложение
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser \
    && mkdir -p /app/uploads /app/logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/ || exit 1

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

