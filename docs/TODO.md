# TODO

Все открытые проблемы проекта. Закрытые — в `docs/CHANGELOG.md`.
Архитектура и графы — в `docs/architecture.md`.

---

## 🔴 Критические

### [ ] N1 — Удаление чата оставляет строки `File` и файлы на диске

**Файлы:** `models/chat.py`, `services/chats.py`

`Chat.messages` — `cascade-delete-orphan`, но FK `Message.file_id` без каскада на `File`,
и `File` не связан с чатом. При удалении чата строки `File` и physical-файлы
в `uploads/<chat_id>/` остаются навсегда (disk leak, висячие ссылки).

**Фикс:** `ondelete="CASCADE"` на FK `Message.file_id` или сервисный хелпер,
удаляющий файлы перед удалением чата.

---

### [ ] N2 — Docker: секреты в образе + dev-режим в проде

**Файлы:** `backend/Dockerfile`, `backend/entrypoint.sh`, `docker-compose.yml`

- `COPY . .` тащит `.env` и приватные RSA-ключи в образ (нет `.dockerignore`)
- `entrypoint.sh` запускает `uvicorn --reload` под `restart: unless-stopped` (dev-режим)
- Нет non-root user, нет HEALTHCHECK
- bind-mount `./backend:/app` перекрывает копию образа

**Фикс:** `.dockerignore`, `USER appuser`, HEALTHCHECK, убрать `--reload`,
dev/prod варианты entrypoint.

---

## 🟡 Недоработки

### [ ] N3 — mypy «чист» за счёт отключённых проверок

**Файл:** `pyproject.toml`

`disable_error_code = union-attr, arg-type, assignment, no-any-return` точечно на
`routes/messages.py`, `routes/files.py`, `routes/chats.py`, `services/websocket_manager.py` —
проверки отключены именно в бизнес-логике; verdict «mypy чистый» отражает override-зоны,
а не покрытие.

**Фикс:** включить проверки, исправить ошибки или сузить override.

---

### [ ] N4 — Три `.env` с расходящимся содержимым

**Файлы:** `./.env`, `./backend/.env`, `./backend/app/.env`

pydantic-settings читает `backend/app/.env`, compose подключает `./backend/.env` для backend
и `./.env` для postgres/redis — три источника правды по DB/REDIS/SECRET_KEY.

**Фикс:** один `.env` в корне, остальные удалить.

---

### [ ] N5 — Нет unique-констрейнта на пару пользователей чата

**Файл:** `models/chat.py`

`users: list[int]` через PostgreSQL ARRAY, но `create` = SELECT + flush без commit →
две параллельные `POST /chats` создают дубликаты одной пары.

**Фикс:** `UNIQUE` constraint или partial index на сортированную пару `user_a_id, user_b_id`.

---

### [ ] N6 — Лимитер не знает про reverse proxy

**Файл:** `services/limiter.py`

`get_remote_address` берёт `request.client.host` без `X-Forwarded-For` —
за reverse proxy все клиенты сливаются в IP прокси, rate limits ломаются.

**Фикс:** `ProxyFix` middleware или настройка trusted headers.

---

### [ ] M9 — `notify_offline` = 2 DB + N WS

**Файл:** `services/presence.py`

Commit перенесён в конец (✅ P1.7), но объём работы не уменьшен:
`SessionDAO.update` + `ChatUserDAO.get_online_users` + N отправок.

**Фикс:** батч-запрос или оптимистичная инвалидация на клиенте.

---

### [ ] M-F — Нет `asyncio.Lock` в `WebSocketManager`

**Файл:** `services/websocket_manager.py`

`connect/disconnect/send_*` мотируют `active_connections` без блокировки;
`was_offline`/`went_offline` вычисляются на её основе — возможна гонка
между параллельными WS-событиями одного пользователя.

**Фикс:** `asyncio.Lock` на `active_connections`.

---

## 🟢 Косметика

### [ ] N7 — `to_dict()` — мёртвый код

**Файлы:** `database.py`, `models/user.py`

`to_dict()` не вызывается нигде.

**Фикс:** удалить.

---

### [ ] N8 — Коллизия имени `FileResponse`

**Файл:** `routes/files.py`

Имя pydantic-схемы `FileResponse` collide со starlette `FileResponse`.

**Фикс:** переименовать в `FileRecordResponse`.

---

### [ ] N9 — `AliasChoices("user_from_id")` — легаси

**Файл:** `schemas/message.py`

В БД только `sender_id`.

**Фикс:** убрать после миграции фронтенда.

---

### [ ] N10 — `get_active`: `-> UserResponse | None`, но `None` не возвращается никогда

**Файл:** `services/chats.py`

Только `raise NotFoundError`.

**Фикс:** сузить сигнатуру до `-> UserResponse`.

---

### [ ] N11 — Захардкоженные константы

**Файлы:** `routes/ws.py`, `services/websocket_manager.py`, `utils/files.py`

`HEARTBEAT_TIMEOUT=90`, `max_connections=1000`, `quality=85`, `WEBP_MAX_WIDTH=1200` —
вынести в `config.py` по образцу v3.1.

---

### [ ] N12 — `send_message(chat_id: str)` при пути `/chats/{chat_id:int}`

**Файл:** `services/messages.py`

Двойное приведение: FastAPI парсит `int`, сервис снова `int(chat_id)`.

**Фикс:** типизировать `int`.

---

### [ ] N13 — Двойная валидация файла

**Файлы:** `utils/files.py`, `services/files.py`

ext+size проверяются и в `save_file`, и в `FileManager.create`.

**Фикс:** оставить одну (в `save_file`).

---

### [ ] N14 — `get_session_manager()` создаёт новый `SessionManager` на каждый запрос

**Файл:** `deps.py`

**Фикс:** синглтон.

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

### [x] `ws.py` — `user_id` из URL-пути не валидируется

**Файл:** `routes/ws.py`

**Наблюдение:** `user_id` берётся из URL, но `session_id → user_id` сверяется;
несовпадение → разрыв соединения. Безопасное поведение.
