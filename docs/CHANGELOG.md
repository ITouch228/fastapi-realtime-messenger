# CHANGELOG ITMessage

История изменений по выпускам и squash-PR. Сохранены исходные записи ранних релизов; актуальные схемы и потоки вынесены в [architecture.md](architecture.md) и [data_flow.md](data_flow.md). Открытые проблемы — [TODO.md](TODO.md).

## PR #15 — Порядок событий presence между воркерами (2026-11-04)

- Атомарный номер версии каждого глобального перехода online/offline в Redis.
- `presence_update` содержит `version`; фронтенд не принимает события старее текущего.
- Интеграционные тесты Redis и регрессионные тесты JavaScript на обратный порядок событий.
- Production по-прежнему использует четыре Uvicorn-воркера.

---

## После v3.2 — стабилизация и инфраструктура (PR #1–#13, 2026-11-04)

| PR | Изменение |
| --- | --- |
| #1 | Проверка WebSocket Origin до авторизации |
| #2 | CI quality gates: Ruff, mypy, ESLint, Prettier |
| #3 | Удаление физических вложений только после DB commit |
| #4 | Автоформатирование Ruff в pre-commit |
| #5 | Redis как общее хранилище rate limits |
| #6 | Redis Pub/Sub для событий WebSocket между процессами |
| #7 | Распределённый online/offline presence через Redis ZSET и TTL |
| #8 | Интеграционные multiworker-тесты, синхронизация после WS reconnect |
| #9 | Исправлен импорт CSRF на страницах login/register без Axios |
| #10 | `backend/.dockerignore` исключает секреты и локальные данные из образа |
| #11 | Безопасные миграции PostgreSQL и полный HTTP smoke с БД и Redis |
| #12 | Docker Compose smoke на четырёх Uvicorn-воркерах, RSA и рестарте |
| #13 | Повторные подписки Redis Pub/Sub и обработка ошибок WS/публикации |

**Текущее состояние:** один `.github/workflows/ci.yml` с независимыми Python, Frontend и Docker Compose jobs. `UVICORN_WORKERS=4` сохранено; линейная история PR через Squash and merge. Документы и графы обновляются отдельным housekeeping-PR без изменения функциональности.

**Нерешённые ограничения:** Pub/Sub не хранит события при сбоях; возможна гонка порядка `presence_update` (N19); физическая очистка файлов после commit не имеет durable queue; браузерный E2E пока не автоматизирован.

---

## v3.2 — Rate-limit за прокси, async-lock в WS, батч-presence, документация

> Исправлена критическая проблема rate limiting за reverse proxy (N6): теперь
> `X-Forwarded-For` доверяется только от доверенных IP/CIDR (`TRUSTED_PROXIES`),
> прямой запрос не может подделать заголовок.
>
> `WebSocketManager` получил `asyncio.Lock` (M-F): все мутации `active_connections`
> атомарны, `disconnect` стал async — гонки при параллельных connect/disconnect
> одного пользователя исключены. `send_personal_message` под локом только снимает
> список и отвязывает мёртвые; `send_json` без блокировки — медленный клиент не
> стопорит остальных. Добавлен `send_to_users` (asyncio.gather) и `online_user_ids`.
>
> `notify_offline` оптимизирован (M9): адресаты берутся из памяти — если никто не
> онлайн, `SELECT` по чатам не выполняется вовсе. Отправка батчем (`asyncio.gather`)
> вместо цикла: время не растёт линейно от числа собеседников. Порядок изменён на
> «прочитать адресатов → UPDATE + commit → разослать» — `presence_update` не
> опережает зафиксированный `last_seen`.
>
> Заодно обновлены README (N21: убраны ссылки на удалённые `backend/.env`),
> `.env.example` (добавлен `TRUSTED_PROXIES`), `docs/TODO.md` (закрыты N6/M-F/M9,
> добавлены N17–N21 — локальность WS/presence/rate-limit для воркера, порядок
> presence-событий, PATH в make lint).

---

## v3.1 — Стабилизация: критические фиксы, безопасность файлов, конфиг, Redis-lifespan, CSRF-страницы

> Крупный релиз: новый слой исключений, сервис presence, миграция `last_seen`,
> рефакторинг фронтенда на модули, полная документация (architecture/data_flow/changelog),
> перевод на `settings` (CORS, rate limits, лимиты файлов/сообщений), Redis-lifespan,
> развязка циклических импортов, CSRF-куки на GET-страницах, сужение `except Exception`,
> `run_in_threadpool` для блокирующего I/O.

### 🔴 Критические

| ID | Файл | Что исправлено |
|----|------|----------------|
| C1 | `routes/messages.py`, `routes/files.py`, `services/messages.py`, `services/files.py` | Нарушение слоёв: роуты больше не обращаются к DAO напрямую. Добавлены `MessageManager.soft_delete`, `FileManager.get`, `FileManager.create` (возвращает `FileInDb`) |
| C2 | `config.py`, `main.py`, `docker-compose.yml`, `.gitignore` | `uploads` вынесены из `STATIC_DIR` в `BASE_DIR/uploads` — файлы больше не публичны через `StaticFiles`. Volume `uploads_data`, `.gitignore: uploads/` |
| C3 | `services/chats.py`, `services/messages.py` | `model_validate(None)` → 500: проверка `is None` до валидации, безопасный `return None` |
| C4 | `database.py`, `routes/auth.py`, `routes/chats.py`, `routes/messages.py` | Unit of Work: убран `commit` из `get_session`; явный `session.commit()` только в write-эндпоинтах (register, delete_chat, send_message, delete_message) |
| C5 | `services/redis_client.py`, `services/session_manager.py`, `main.py` | Инициализация Redis через `init_redis()` в lifespan (до `yield`), `get_redis()` без блокировок; `close_redis()` после `yield` + `await engine.dispose()` |
| B2 | `static/js/app.js` | Открытие чата: рендер из стора сразу, без очистки контейнера до сетевого ответа — сообщения не пропадают при offline/ошибке запроса |
| B3 | `static/js/core/api.js` | Обработчик 401 использовал неопределённую `url` (ReferenceError) — авто-refresh был сломан. Исправлено на `original.url` |

### 🟡 Недоработки

| ID | Файл | Что сделано |
|----|------|-------------|
| W2 | `dao/dao.py`, `services/messages.py`, `routes/messages.py` | `get_chat_messages`: чат + сообщения одним запросом (`MessageDAO.find_by_chat_with_chat`, outerjoin) + батч-резолв файлов (`FileDAO.find_by_ids`) — устранён N+1 |
| W3 | `dao/dao.py`, `services/messages.py` | `delete`: сообщение + участники чата одним запросом (`MessageDAO.find_with_chat_users`), проверки автора/членства в Python |
| W6 | `routes/auth.py`, `services/auth.py` | `login/logout/refresh` → `AuthManager.create_session` / `revoke_session` / `rotate_session` |
| W7 | `routes/auth.py` | Хелпер `_auth_response` вместо дублирования `set_cookie` в login и refresh |
| W8 | `routes/messages.py`, `static/js/core/wsHandler.js` | `new_message` шлётся **всем** участникам (включая отправителя), payload содержит `client_id` |
| W9 | `static/js/core/store.js`, `static/js/features/send.js` | Optimistic confirm по `client_id` (uuid), не по тексту; `confirmMessage` идемпотентен |
| W10 | `static/js/core/store.js`, `static/js/features/messages.js` | Нормализация ключей Map (`_normalizeChatId`), флаг `loaded`/`isLoaded` вместо `hasMessages` (size>0) |
| W11 | `utils/csrf.py`, `utils/cookies.py`, `routes/{auth,messages,chats}.py`, `static/js/core/api.js` | CSRF Double Submit Cookie: кука `csrftoken` + заголовок `X-CSRF-Token` |
| — | `routes/messages.py`, `static/js/features/send.js`, `static/js/core/store.js`, `static/js/features/chats.js` | Temp-чат: `peer_id` в FormData вместо `chat_id.split('-')`; `store.replaceTempChat(tempId, realId)` переносит чат/сообщения/флаги/DOM-узел/activeChatId |

### 🟢 Безопасность файлов (S1–S5)

| ID | Файл | Что исправлено |
|----|------|----------------|
| S1 | `static/js/ui/imageLoader.js` | Импорт `from 'static/...'` → `from '/static/js/core/constants.js'` — относительный путь не резолвился |
| S2 | `static/js/ui/imageLoader.js` | Убран `priority: 'high'` из `fetch()` — не-стандартное свойство |
| S3 | `routes/files.py` | `width: float = Query(None, ge=1, le=4000)`, `quality: int = Query(None, ge=1, le=100)` — дефолт `Query(70)` делал ветки `quality or 60/80` мёртвыми |
| S4 | `utils/files.py` | `resolve_file_path`: `str().startswith()` → `Path.is_relative_to()` — обход traversal |
| S5 | `utils/validators.py` | Новая `validate_file_name()` (reject: пустое, `/`, `\`, `.`, `..`, ctrl, >255) |

### 🟢 Сервисы (M-A, M-C, M-E)

| ID | Файл | Что исправлено |
|----|------|----------------|
| M-A | `services/chats.py::ChatManager.create` | `BadRequestError` при `user_a_id == user_b_id`; `users=sorted(...)` для детерминизма |
| M-C | `services/files.py::FileManager.create` | `FileDAO.add` в `begin_nested()` (savepoint); `except IntegrityError` → повторный поиск по `rel_path` |
| M-E | `routes/messages.py::send_message` | Guard «пустое сообщение без файла» на бэкенде |

### 🔴 Исправлено (стабильность и производительность)

| ID | Файл | Что исправлено |
|----|------|----------------|
| P0.1 | `utils/files.py`, `routes/messages.py` | `save_file` больше не возвращает `bool` — при `OSError` бросает `AppError`; роутер не проверяет `success` |
| P0.2 | `services/files.py`, `routes/files.py` | `os.path.exists` / `resolve_file_path` → `run_in_threadpool` — блокирующий I/O убран |
| P0.3 | `main.py` | `await engine.dispose()` в lifespan после `yield` — пул закрывается при shutdown |
| P0.4 | `utils/security.py`, `deps.py`, `utils/__init__.py` | Цикл `utils → security → deps → schemas → utils` развязан: `pwd_context` → `utils/security.py` |
| P0.4b | `services/__init__.py`, `services/auth.py`, `services/sessions.py` | Цикл `services/__init__ ↔ auth/sessions` развязан импортами через конкретные модули |
| P0.5 | `routes/pages.py`, `utils/security.py` | CSRF-кука на GET-страницах login/register через `generate_csrf_token()` + `set_csrf_cookie()` |
| P0.6 | `utils/files.py` | `compress_image_sync`: двойной `.save()` в один буфер (PNG+RGBA → 0 bytes) → три взаимоисключающие ветки |
| P1.7 | `services/presence.py` | `notify_offline`: `commit()` посередине убран, один `await session.commit()` в конце |
| P1.8 | `exceptions/handlers.py` | `AppError` со `status_code < 500` логируется как `warning`, а не `error` |
| P1.10 | `core/api.js`, `features/login.js`, `features/register.js` | `getCsrfToken` — экспорт из `core/api.js`, локальные дубли удалены |
| P2.1 | `dao/base.py` | `BaseDAO(Generic[ModelT])` → `BaseDAO[ModelT: Base]` (PEP 695, Python 3.12) |
| P2.5 | `config.py` | Отсутствие `PRIVATE_KEY`/`PUBLIC_KEY` → понятный `RuntimeError` с openssl-подсказкой |

### 🟡 Конфиг (M4, M10)

| ID | Файл | Что исправлено |
|----|------|----------------|
| M4 | `config.py`, `main.py` | CORS: `allow_origins=settings.ALLOWED_ORIGINS` вместо хардкода |
| M10 | `config.py`, `routes/auth.py`, `routes/pages.py`, `routes/messages.py`, `utils/files.py` | Rate limits, `MAX_MESSAGE_LENGTH`, `MAX_FILE_SIZE`, `ALLOWED_FILE_EXTENSIONS` → `config.py`; `get_db_url()` → `@property db_url` |

### 🟡 Логирование и исключения (M7)

| ID | Файл | Что исправлено |
|----|------|----------------|
| M7 | `routes/ws.py`, `routes/messages.py`, `services/websocket_manager.py`, `services/files.py`, `utils/files.py` | `except Exception` → конкретные типы; штатные WS-обрывы → `info`; программные ошибки → `critical + raise`; `finally` гарантирует disconnect + `notify_offline` |

### 🟢 Косметика (закрыто)

| ID | Что |
|----|-----|
| DUP1 | `trim` только на уровне схем — DAO не триммит повторно |
| DUP2 | `_build_chat_response()` — общий хелпер для `get_by_user`/`get_by_users` |

### 🟢 Косметика (отложено)

| ID | Файл | Почему отложено |
|----|------|----------------|
| M1 | `schemas/*`, `dao/*` | camelCase на фронте vs snake_case в API — нет явного маппинга |
| M-D | `core/wsHandler.js:41` | `Number(msg.chat_id)` — сервер шлёт реальные int-id, риск минимален |
| M-F | `services/websocket_manager.py` | Нет `asyncio.Lock` для `active_connections` — race при `was_offline`/`went_offline` |
| M8 | `services/auth.py` | `Depends()` внутри `@staticmethod` — псевдо-ООП стиль оставляем как есть |

### 🏗️ Архитектура

- **Слой исключений** (`app/exceptions/`): `AppError` + typed-ошибки и централизованные `handlers.py`.
- **Сервис presence** (`app/services/presence.py`): `notify_online`/`notify_offline`, рассылка `presence_update`, запись `last_seen`.
- **Миграция** `05_add_user_last_seen` + `last_seen` в `models/user.py`.
- **DAO**: оконные функции для списка чатов, `find_by_chat_with_chat`, `find_with_chat_users`, `find_by_ids`.
- **Сервисы**: бизнес-логика в `AuthManager`/`MessageManager`/`UserManager`/`ChatManager`/`FileManager`.
- **Конфиг** (`config.py`): единый источник настроек — `db_url` (property), `ALLOWED_ORIGINS`, rate limits, лимиты сообщений/файлов, расширения.
- **Redis**: явная инициализация в lifespan вместо lazy-инициализации под локом.
- **Схемы**: ре-экспорт через `__init__.py`; удалены `common.py`, `MessageCreate`, `FileCreate`.
- **Утилиты**: `utils/csrf.py`, `utils/validators.py`, `utils/security.py` (`pwd_context`); CSRF-логика в `utils/cookies.py`.
- **Фронтенд**: модульная структура без сборщика — `core/` / `features/` / `ui/`, композиция в `app.js`. Единый источник разметки — `createMessageEl`.
- **Документация**: `docs/architecture.md`, `docs/data_flow.md`, этот `CHANGELOG.md`.

### 🧹 Мёртвый код (удалено)

- `MessageDAO.list_messages` (не вызывался).
- `MessageDAO.find_all` (не вызывался, M6).
- `services/event_bus.py`.
- `schemas/common.py`, схемы `MessageCreate`, `FileCreate`.
- `tools/quality.py`.
- Старый фронтенд: `main.js`, `messages.js`, `state.js`, `messageHandler.js`, `websocket.js`.
- Мёртвые импорты/логгеры в `routes/chats.py`, `routes/files.py`.

### ✅ Проверки

- `ruff check backend/app/` — All checks passed.
- `from app.main import app` — OK.
- `npx eslint core/api.js features/login.js features/register.js` — OK.
- ⚠️ `mypy` локально не установлен; тесты в репозитории отсутствуют.

---

## v2.0 — Развязка API и веба, Redis-сессии, чистые слои

## v1.0 — Первый рабочий релиз
