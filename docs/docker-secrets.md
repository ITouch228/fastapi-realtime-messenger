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

4. Для безопасной проверки **содержимого нового образа**, не публикуя его,
   используйте временный контейнер. В образе не должно быть `/app/keys/private.pem`
   или локального `.env`. Успешная проверка путей не отменяет необходимости
   контролировать слои и историю ранее собранных образов.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh backend -c 'test ! -e /app/keys/private.pem || echo "Ключ присутствует через runtime mount; это ожидаемо"'
```

> Обратите внимание: при выполнении через Compose файл ключа может
> присутствовать из-за подключённого read-only тома. Это **не доказывает**,
> что ключ находится в образе. Для проверки самого образа запускайте
> `docker run --rm --entrypoint sh <image> -c 'test ! -e /app/keys/private.pem'`
> без volume mounts.
