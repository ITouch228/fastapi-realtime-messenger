# CHANGELOG ITMessage

Список всех изменений и исправлений. Один блок — один коммит.
Полная детализация проблем — в `docs/architecture.md` (§5 сводка, §7 фиксы)
и `docs/data_flow.md` (флоу).

---

## v3.0 — Стабилизация: критические фиксы, закрытие недоработок, документация

> Крупный релиз: новый слой исключений, сервис presence, миграция `last_seen`,
> рефакторинг фронтенда на модули, полная документация (architecture/data_flow/changelog).

### 🔴 Критические (C1–C5, B2, B3)

| ID | Файл | Что исправлено |
|----|------|----------------|
| C1 | `routes/messages.py`, `routes/files.py`, `services/messages.py`, `services/files.py` | Нарушение слоёв: роуты больше не обращаются к DAO напрямую. Добавлены `MessageManager.soft_delete`, `FileManager.get`, `FileManager.create` (возвращает `FileInDb`) |
| C2 | `config.py`, `main.py`, `docker-compose.yml`, `.gitignore` | `uploads` вынесены из `STATIC_DIR` в `BASE_DIR/uploads` — файлы больше не публичны через `StaticFiles`. Volume `uploads_data`, `.gitignore: uploads/` |
| C3 | `services/chats.py`, `services/messages.py` | `model_validate(None)` → 500: проверка `is None` до валидации, безопасный `return None` |
| C4 | `database.py`, `routes/auth.py`, `routes/chats.py`, `routes/messages.py` | Unit of Work: убран `commit` из `get_session`; явный `session.commit()` только в write-эндпоинтах (register, delete_chat, send_message, delete_message) |
| C5 | `services/redis_client.py` | Race в `get_redis`: `asyncio.Lock` + double-checked locking, `close_redis` тоже под локом. Побочно: circular import в `utils/files.py` (`from app.utils.logging import get_logger`) |
| B2 | `static/js/app.js` | Открытие чата: рендер из стора сразу, без очистки контейнера до сетевого ответа — сообщения не пропадают при offline/ошибке запроса |
| B3 | `static/js/core/api.js` | Обработчик 401 использовал неопределённую `url` (ReferenceError) — авто-refresh был сломан. Исправлено на `original.url` |

### 🟡 Недоработки (W2, W3, W7–W11)

| ID | Файл | Что сделано |
|----|------|-------------|
| W2 | `dao/dao.py`, `services/messages.py`, `routes/messages.py` | `get_chat_messages`: чат + сообщения одним запросом (`MessageDAO.find_by_chat_with_chat`, outerjoin) + батч-резолв файлов (`FileDAO.find_by_ids`) — устранён N+1 |
| W3 | `dao/dao.py`, `services/messages.py` | `delete`: сообщение + участники чата одним запросом (`MessageDAO.find_with_chat_users`), проверки автора/членства в Python |
| W7 | `routes/auth.py` | Хелпер `_auth_response` вместо дублирования `set_cookie` в login и refresh |
| W8 | `routes/messages.py`, `static/js/core/wsHandler.js` | `new_message` шлётся **всем** участникам (включая отправителя), payload содержит `client_id` |
| W9 | `static/js/core/store.js`, `static/js/features/send.js` | Optimistic confirm по `client_id` (uuid), не по тексту; `confirmMessage` идемпотентен (client_id → реальный id → новое) |
| W10 | `static/js/core/store.js`, `static/js/features/messages.js` | Нормализация ключей Map (`_normalizeChatId`), флаг `loaded`/`isLoaded` вместо `hasMessages` (size>0) |
| W11 | `utils/csrf.py`, `utils/cookies.py`, `routes/{auth,messages,chats}.py`, `static/js/core/api.js` | CSRF Double Submit Cookie: кука `csrftoken` + заголовок `X-CSRF-Token` на logout/refresh/send/delete |
| — | `routes/messages.py`, `static/js/features/send.js`, `static/js/core/store.js`, `static/js/features/chats.js` | Temp-чат: `peer_id` в FormData вместо `chat_id.split('-')`; `store.replaceTempChat(tempId, realId)` переносит чат/сообщения/флаги/DOM-узел/activeChatId |

### 🐛 Баги

| ID | Файл | Что исправлено |
|----|------|----------------|
| B1 | `static/js/features/send.js`, `static/js/ui/messageView.js` | Файл не рендерился в подтверждённом сообщении: optimistic `message_file_id: -1` + `updateMessageInDom` пересоздаёт элемент, если в подтверждении пришёл файл |

### 🏗️ Архитектура и рефакторинг

- **Слой исключений** (`app/exceptions/`): `AppError` + typed-ошибки
  (`BadRequestError`, `UnauthorizedError`, `PermissionDeniedError`,
  `NotFoundError`, `ConflictError`, `PayloadTooLargeError`) и централизованные
  `handlers.py`. Все `HTTPException` в роутах заменены на typed-исключения.
- **Сервис presence** (`app/services/presence.py`): `notify_online`/`notify_offline`,
  рассылка `presence_update` собеседникам, запись `last_seen`.
- **Миграция** `05_add_user_last_seen` + `last_seen` в `models/user.py`.
- **DAO**: `MessageDAO.find_by_chat_with_chat`, `find_with_chat_users`,
  `FileDAO.find_by_ids`, `ChatDAO.get_peers`, оконные функции для списка чатов.
- **Сервисы**: бизнес-логика в `AuthManager` (`create_session`/`revoke_session`/
  `rotate_session`, `_generate_tokens`), `MessageManager`
  (`get_chat_messages`/`delete`/`build_message_responses`), `UserManager`,
  `ChatManager`, `FileManager`. Роуты — тонкая HTTP-обвязка.
- **Схемы**: ре-экспорт через `__init__.py`; удалён `common.py`; удалены мёртвые
  `MessageCreate`, `FileCreate`.
- **Утилиты**: новый `utils/csrf.py`, `utils/validators.py`; `logging_config.py` →
  `logging.py`; CSRF-логика в `utils/cookies.py`.
- **Фронтенд**: модульная структура без сборщика — `core/` (`store.js`, `socket.js`,
  `wsHandler.js`, `api.js`, `constants.js`), `features/` (`chats`, `messages`,
  `send`, `search`, `auth`, `login`, `register`), `ui/` (`messageView`,
  `imageLoader`, `wsStatus`, `lightbox`, `badge`), композиция в `app.js`.
  Единый источник разметки сообщения — `createMessageEl`.
- **Документация**: `docs/architecture.md`, `docs/data_flow.md`, этот `CHANGELOG.md`.
- **Инфра/конфиг**: `docker-compose.yml` (volume `uploads_data`), `.gitignore`
  (`uploads/`), `Makefile` (цели `lint`/`lint-back`/`lint-front`/`check`),
  `package.json` (eslint/prettier).

### 🧹 Мёртвый код (удалено)

- `MessageDAO.list_messages` (не вызывался).
- `services/event_bus.py`.
- `schemas/common.py`, схемы `MessageCreate`, `FileCreate`.
- `tools/quality.py`.
- Старый фронтенд: `main.js`, `messages.js`, `state.js`, `messageHandler.js`,
  `websocket.js`, старые `login.js`/`register.js` (перенесены в `features/`).
- Мёртвые импорты/логгеры в `routes/chats.py`, `routes/files.py`.

### 🟢 Косметика (отложено до следующего патча)

Помечено в коде `# TODO: [SMELL]/[CONFIG]/[DUP]/[PERF]` со ссылкой на
`docs/architecture.md` §5.

- M1 — camelCase на фронте vs snake_case в API (нет явного маппинга).
- M4 — CORS origins захардкожены (`main.py`) → `settings.ALLOWED_ORIGINS`.
- M5 — `IMAGE_LOAD_TIMEOUT` / `IMAGE_PLACEHOLDER` захардкожены (`ui/imageLoader.js`, `ui/messageView.js`).
- M6 — `find_all` без `order_by` (`dao/base.py`).
- M7 — `except Exception` вместо конкретных типов (`routes/ws.py`, `services/files.py`, `services/websocket_manager.py`, `utils/files.py`).
- M8 — `Depends()` внутри `@staticmethod` (`services/auth.py`).
- M9 — `notify_offline`: 2 DB-запроса + N WS-сообщений (`services/presence.py`).
- M10 — константы разбросаны (`core/constants.js`, `ui/imageLoader.js`).
- M11 — `isAuthRoute` по строке URL (`core/api.js`).
- DUP1 — `trim` дублируется (схема + DAO, `schemas/user.py`).
- DUP2 — `_build_chat_response` дублируется (`services/chats.py`).

### ✅ Проверки

- `ruff check .` — All checks passed.
- `ruff format --check .` — 50 files already formatted.
- `mypy --package app` — **0 ошибок** (было 3: `dao/base.py` `no-any-return`,
  закрыты через `typing.cast`).
- `node --check` по всем 19 JS-файлам — OK.
- `from app.main import app` — OK.
- ⚠️ `eslint` / `prettier` локально не прогнаны (нет в `node_modules`) — прогнать
  через `make lint-front` перед коммитом.

---

## v2.0 — Развязка API и веба, Redis-сессии, чистые слои

## v1.0 — Первый рабочий релиз
