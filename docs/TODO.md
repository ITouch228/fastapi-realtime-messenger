# TODO

Все открытые проблемы проекта. Закрытые — в `docs/CHANGELOG.md`.
Архитектура и графы — в `docs/architecture.md`.

---

## 🔴 Критические

### [x] N1 — Удаление чата оставляет строки `File` и файлы на диске

**Файлы:** `services/chats.py`, `services/files.py`, `dao/dao.py`, `utils/files.py`

**Фикс (2026-11-04, PR #3):** `FileManager.delete_chat_files` удаляет только строки в транзакции и возвращает пути файлов. После `ChatManager.delete` роут выполняет `session.commit()`, и лишь затем вызывает `FileManager.cleanup_deleted_chat_files`. При ошибке commit физические файлы остаются на диске; ошибка cleanup после commit логируется и не меняет уже успешный ответ HTTP.

**Ограничение:** если процесс остановится между commit и cleanup либо диск недоступен, остаются осиротевшие файлы. Для строгой гарантии очистки потребуется durable cleanup queue/outbox с повторными попытками и периодической сверкой.

---

### [x] N2 — Docker: секреты в образе + dev-режим в проде

**Файлы:** `backend/Dockerfile`, `backend/entrypoint.sh`, `backend/.dockerignore`, `docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.prod.yml`

**Исправлено и проверено (PR #10, #12):** разделение dev/prod, исключение секретов и автоматический Docker Compose smoke с четырьмя Uvicorn-воркерами.
- `.dockerignore` — `.env`, `keys/`, `logs/`, `uploads/`, кэш не попадают в образ.
- `Dockerfile` — non-root `appuser` (uid 10001), `HEALTHCHECK`, `--reload` убран из образа.
- `entrypoint.sh` — режим по env: `UVICORN_RELOAD=1` → `--reload` (dev), иначе `--workers N` (prod).
- `docker-compose.yml` (base, prod-safe) — без bind-mount кода; uploads в volume, `keys/` смонтированы read-only.
- `docker-compose.override.yml` (dev, авто) — bind-mount `./backend:/app` + `--reload`.
- `docker-compose.prod.yml` (prod, явно) — без bind-mount, 4 воркера, `restart: always`.
- Makefile: `make dev` / `make prod`.

---

## 🟡 Недоработки

### [x] N3 — mypy «чист» за счёт отключённых проверок

**Файл:** `pyproject.toml`

**Фикс (2026-10-25):** override `disable_error_code = union-attr, arg-type, assignment, no-any-return`
для `app.routes.*` + `services.{files,messages,auth,users,chats}` полностью удалён — проверки
включены на всей бизнес-логике. Реальная ошибка типов была одна: `BaseDAO.find_one_or_none`
возвращал `Any` из `scalar_one_or_none()` → закрыта через `cast(ModelT | None, ...)`.
Дополнительно убрана неиспользуемая секция `migration.*` (не грузится при `mypy --package app`,
мешала `warn_unused_configs`). `mypy --package app` — 0 ошибок на холодном кэше (exit 0).

---

### [x] N4 — Три `.env` с расходящимся содержимым

**Файлы:** `.env`, `.env.example`, `backend/app/config.py`, `docker-compose.yml`

**Фикс (2026-10-25):** один `.env` в корне репозитория. `backend/.env`, `backend/app/.env`
(и их `.env.example`) удалены. `config.py` читает `REPO_ROOT/.env` (в контейнере файла нет —
настройки приходят через `env_file` compose в OS env). `docker-compose.yml` подключает
корневой `.env` и для postgres, и для backend; в `environment:` backend оставлены только
сетеспецифичные `DB_HOST`/`REDIS_URL`. Устранена рассинхронизация `DB_NAME`
(`messanger_db` в `backend/.env` vs `messenger_db` в остальных).

---

### [x] N5 — Нет unique-констрейнта на пару пользователей чата

**Файлы:** `models/chat.py`, `services/chats.py`, `migration/versions/06_..._unique_index.py`

**Актуально после PR #11:** `users` хранится отсортированным (`sorted([user_a, user_b])`).
Уникальный B-tree индекс создан непосредственно по PostgreSQL `integer[]`;
выражение `array_to_string` удалено, поскольку не подходит для expression-индекса.
Миграция **не удаляет** дубликаты: при обнаружении их нужно сначала безопасно
объединить вручную. `ChatManager.create` использует `begin_nested()` и обрабатывает
`IntegrityError`, возвращая существующий чат при конкурентном создании.

---

### [x] N6 — Лимитер не знает про reverse proxy

**Файлы:** `services/limiter.py`, `config.py`, `.env.example`

**Фикс (2026-10-29):** вместо `get_remote_address` — собственный `get_client_ip`.
`X-Forwarded-For` учитывается только если соединение пришло от адреса из новой
настройки `TRUSTED_PROXIES` (IP или CIDR, по умолчанию пусто → поведение как раньше,
подделать клиента заголовком при прямом запросе нельзя). Заголовок читается справа
налево: пропускаются доверенные прокси, первый недоверенный — клиент, поэтому
цепочка `nginx → Caddy → app` работает, если все узлы в списке. Разбор `TRUSTED_PROXIES`
под `lru_cache`, кривые значения молча отбрасываются (опечатка в `.env` не роняет старт).

---

### [x] M9 — `notify_offline` = 2 DB + N WS

**Файлы:** `services/presence.py`, `services/websocket_manager.py`, `routes/messages.py`

**Фикс (2026-10-29):** `_online_peers()` — адресаты берутся из памяти, а не из БД:
снимок `manager.online_user_ids()` и только если кто-то онлайн — один `ChatDAO.get_peers`
и пересечение. Никто не подключён → SELECT не выполняется вовсе, остаётся 1 DB-операция.
Отправка — `manager.send_to_users(payload, targets)` одним `asyncio.gather`: время
рассылки больше не растёт линейно от числа собеседников (3 клиента по 20 мс вместо
60 мс → 20 мс). Порядок изменён на «прочитать адресатов → UPDATE + commit → разослать»,
так что `presence_update` не опережает зафиксанный `last_seen` (раньше коммит был
после отправок). Тот же батч применён в `routes/messages.py` (`new_chat`, `new_message`).

---

### [x] M-F — Нет `asyncio.Lock` в `WebSocketManager`

**Файл:** `services/websocket_manager.py`, `routes/ws.py`

**Фикс (2026-10-29):** все мутации `active_connections` (`connect`/`disconnect`/снятие
мёртвых сокетов) под `asyncio.Lock`, `disconnect` стал `async` (обновлён `finally`
в `routes/ws.py`). `send_*` под локом только берут снимок списка и отвязывают мёртвые —
`send_json` выполняется без блокировки, иначе медленный клиент стопорил бы рассылку
остальным, а вложенный `disconnect` ловил бы собственный лок. `is_online` остался
синхронным: чтение словаря без `await` в asyncio атомарно. Проверено гонкой:
20 параллельных `connect` → ровно один `was_offline=True`, 20 параллельных
`disconnect` → ровно один `went_offline=True`.

---

### [x] N17 — WS-состояние и presence локальны для процесса воркера

**Исправление (2026-11-04, PR #6–#8):** через Redis Pub/Sub каждый воркер
получает события для своих локальных WebSocket-клиентов. Redis ZSET с отдельным
токеном и TTL для каждой вкладки даёт общий статус online/offline; переходы
регистрации/отключения защищены атомарными Lua-скриптами. При запросе чатов
presence читается из Redis, а не из локального словаря воркера.

**После PR #13:** подписчик повторно подключается при отказе Redis, ошибки
повторной подписки и освобождения WebSocket не обрывают фоновую задачу.
**Ограничение:** Pub/Sub не гарантирует доставку во время обрыва соединения
или рестарта подписчика — история сообщений должна восстанавливаться через API.
После аварийного завершения воркера истёкшая аренда станет offline в API,
но мгновенное уведомление по истечении TTL не отправляется.

---

### [x] N18 — Rate limit считается в памяти процесса

**Файл:** `services/limiter.py`

**Исправление (2026-11-04):** `Limiter` использует `storage_uri=settings.REDIS_URL`,
поэтому воркеры разделяют одни счётчики лимитов регистрации и входа.
Добавлен unit-тест, проверяющий Redis-хранилище вместо памяти процесса.

**Эксплуатация:** Redis должен быть доступен при обработке ограничиваемых запросов.
При его недоступности операции с лимитером могут завершаться ошибкой;
проверить поведение при отказе Redis отдельным интеграционным тестом.

---

### [x] N19 — Presence-события могут прийти в обратном порядке

**Файлы:** `services/presence.py`, `routes/ws.py`

**Исправлено:** атомарные Lua-операции Redis при каждом глобальном переходе
online/offline увеличивают `itmessage:presence:versions` (`HINCRBY`) и
возвращают монотонную версию. WebSocket-уведомления передают её, а
`core/store.js:setPeerStatus` игнорирует устаревшие либо повторные версии.
Две вкладки одного пользователя не создают лишних переходов.

Покрыто интеграционным тестом двух менеджеров Redis и тестами JS на
запоздавшее offline; четыре Uvicorn-воркера по-прежнему проверяются CI.
После потери Redis ключ версий может сброситься — это отдельный
эксплуатационный случай для дальнейшего восстановления.

---

## 🧭 Следующие этапы

- [ ] **Durable cleanup:** периодическая очистка осиротевших файлов или outbox.
- [ ] **Browser E2E:** два аккаунта/несколько вкладок, WebSocket reconnect и работа файлов.
- [ ] **Эксплуатация:** автоматические резервные копии, восстановление БД и uploads, readiness.
- [x] **PR #16, файловое хранилище:** уникальные UUID-пути, атомарная защита от перезаписи, реальные MIME и размер сохранённых байтов.
- [x] **PR #17, транзакции:** удаление только нового UUID-файла при неуспешном создании сообщения или commit; тесты ошибок и отмены запроса. При неоднозначном результате commit (потеря сетевого подтверждения) строгую согласованность обеспечит будущая сверка файлов и БД.

Реализованные после PR #13 возможности и CI описаны в [architecture.md](architecture.md),
[ci.md](ci.md) и [ws-multiworker.md](ws-multiworker.md).

---

## 🟢 Косметика

### [x] N7 — `to_dict()` — мёртвый код

**Файлы:** `database.py`, `models/user.py`

**Фикс (2026-10-25):** `to_dict()` удалён из `Base` и `User`, убран неиспользуемый импорт `class_mapper` из `database.py`.

---

### [x] N8 — Коллизия имени `FileResponse`

**Файл:** `schemas/file.py`

**Решение (2026-10-27):** не трогать — pydantic-схема и starlette `FileResponse` не пересекаются, влияние нулевое.

---

### [x] N9 — `AliasChoices("user_from_id")` — легаси

**Файл:** `schemas/message.py`

**Фикс (2026-10-27):** удалён `validation_alias=AliasChoices("sender_id", "user_from_id")` и устаревшие `model_config`/импорты. ORM-модель и фронт оба используют `sender_id`; алиас был нужен только в переходный период после миграции `45c5351c41f0`.

---

### [x] N10 — `get_active`: `-> UserResponse | None`, но `None` не возвращается никогда

**Файлы:** `services/users.py`, `routes/ws.py`

**Фикс (2026-10-25):** контракт — бросающий (`get_active` поднимает `NotFoundError`/`UnauthorizedError`), согласован с остальными методами и с двумя другими вызовами (`rotate_session`, `get_user_by_token`, которые их ловят). Сигнатура сужена до `-> UserResponse`. В `routes/ws.py` мёртвая проверка `if not await get_active(...)` заменена на явный `try/except (NotFoundError, UnauthorizedError) → close(4404)` (в WS нет HTTP exception handlers).

---

### [x] N11 — Захардкоженные константы

**Файлы:** `config.py`, `routes/ws.py`, `routes/files.py`, `utils/files.py`

**Фикс (2026-10-27):** вынесено в `Settings`: `WS_HEARTBEAT_TIMEOUT=25`,
`IMAGE_SAVE_QUALITY=85`, `IMAGE_QUALITY_MOBILE=60`, `IMAGE_QUALITY_DESKTOP=80`,
`IMAGE_WIDTH_MOBILE=800`, `IMAGE_WIDTH_DESKTOP=1200`. Роуты и утилиты читают `settings`.

---

### [x] N13 — Двойная проверка `MAX_FILE_SIZE`

**Файлы:** `routes/messages.py`, `utils/files.py`

**Фикс (2026-10-27):** удалена дубль-проверка размера файла из роута; остаётся только в `save_file` (утилита).

---

### [x] N15 — Создание `new_chat` payload через схему

**Файл:** `routes/messages.py`

**Фикс (2026-10-27):** payload собирается через `ChatResponse.model_validate(...).model_dump(mode='json')` — нет дублирования dict-литерала, один источник истины.

---

### [ ] N14 — `get_session_manager()` создаёт новый `SessionManager` на каждый запрос

**Файл:** `services/session_manager.py` (используется через `Depends` в `deps.py`, `routes/ws.py`)

Возвращает новый `SessionManager` на каждый вызов. Дёшево (redis-клиент — общий синглтон,
сам менеджер stateless), но лишние аллокации.

**Фикс:** синглтон.

---

### [ ] N16 — `WebSocketManager.broadcast` — мёртвый код

**Файл:** `services/websocket_manager.py`

Метод определён, но не вызывается нигде в проекте (рассылки идут через
`send_personal_message` по участникам чата).

**Фикс:** удалить либо начать использовать (например, для системных событий).

---

### [x] N21 — README ссылается на удалённые `backend/.env` / `backend/.env.example`

**Файл:** `README.md`

**Фикс (2026-10-29):** N4 удалил `backend/.env.example` и `backend/.env`, но README продолжал ссылаться на них в шагах «Быстрый старт» и «Локально по http». Обновлено: один `.env` в корне, `.venv` тоже в корне.

---

### [ ] N20 — `make lint` работает только с ruff/mypy на PATH

**Файл:** `Makefile`

Цели `lint-back`/`format-back` зовут `ruff` и `mypy` напрямую. В репозитории есть
`.venv/` (в `.gitignore`) с `requirements-dev.txt`, но без его активации `make lint`
падает на `mypy: command not found` — проверка «через Makefile» проходит лишь
частично (ruff при этом находится).

**Фикс:** `PYTHON ?= python3` + `$(PYTHON) -m ruff ... / $(PYTHON) -m mypy ...`,
чтобы использовался интерпретатор активного окружения.

---

## ✅ Принято как есть (осознанные решения)

### [x] M1 — camelCase на фронте vs snake_case в API

Маппинг не вводили — работает через alias-поля.

---

### [x] M8 — `Depends()` внутри `@staticmethod`

**Решение (2026-10-23):** псевдо-ООП стиль оставляем, не рефакторим.

---

### [x] M-D — `Number(msg.chat_id)` в `wsHandler.js`

Нормализация, сервер шлёт int — риск минимален.

---

### [x] `config._retry` — мутация axios config без `Object.freeze`

**Файл:** `static/js/core/api.js`

**Наблюдение:** нормально для axios, принято.

---

### [x] `KeyboardInterrupt` — uvicorn обрабатывает сигналы самостоятельно

**Наблюдение:** `except Exception` не ловит `KeyboardInterrupt` (это `BaseException`).
Не проблема.

---

### [x] `Database.get_session` не закрывает сессию явно

**Файл:** `database.py`

**Наблюдение:** `async_session_maker` как `contextmanager` уже делает `await session.close()`
при выходе. Явный rollback только на exception — ок.

---

### [x] N12 — `send_message(chat_id: str)` + `int(chat_id)`

**Файлы:** `routes/messages.py`, `static/js` (`send.js`)

**Решение (2026-10-27):** оставляем как есть — осознанно: временный чат отправляет
`"temp-<peerId>"` в FormData, поэтому параметр принимает строку и приводит её к `int`.

---

### [x] `ws.py` — `user_id` из URL-пути не валидируется

**Файл:** `routes/ws.py`

**Наблюдение:** `user_id` берётся из URL, но `session_id → user_id` сверяется;
несовпадение → разрыв соединения. Безопасное поведение.
