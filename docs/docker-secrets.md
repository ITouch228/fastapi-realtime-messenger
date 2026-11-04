# Проверка секретов и разрешений Docker

Файл `backend/.dockerignore` исключает `keys/`, `.env`, `uploads/` и `logs/`
из контекста сборки Docker. Секреты поступают только через runtime mount.

В `docker-compose.yml` RSA-ключи монтируются из `./backend/keys` в
`/app/keys:ro`, а backend работает под непривилегированным UID `10001`.

1. Создайте ключи локально (см. README), **не добавляйте их в Git**.
2. Перед запуском убедитесь, что UID 10001 может читать оба PEM-файла.
   Владельцу ключей не обязательно совпадать с UID приложения, но права
   должны давать ему доступ к файлам и проход по родительскому каталогу.
   Не назначайте приватному ключу права `777` или общий доступ для всех.
3. Выполните проверку окончательной конфигурации:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend
```

4. Проверьте именно **образ без runtime-монтирования**, а не запущенный Compose-контейнер:

```bash
IMAGE_ID=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml images -q backend)
docker run --rm --entrypoint sh "$IMAGE_ID" -c 'test ! -e /app/keys/private.pem && test ! -e /app/keys/public.pem && test ! -e /app/.env'
```

5. Для проверки прав внутри уже запущенного контейнера:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend python -c "from pathlib import Path; assert Path('/app/keys/private.pem').is_file(); assert Path('/app/keys/public.pem').is_file()"
```

Это проверяет наличие, но для полной проверки чтения можно вызвать `read_text()`
под UID приложения. Реальные production-ключи не выводите в логи.

GitHub Actions автоматически проверяет отсутствие ключей в образе, runtime-права
в контейнере и работу четырёх Uvicorn-воркеров в `docker_compose` job
[единого CI](ci.md). Локальные права на Windows могут отличаться от Linux CI.

> **Важно:** файл ключа будет виден внутри Compose-контейнера из-за read-only
> volume. Это нормально и **не** означает, что он встроен в образ.
