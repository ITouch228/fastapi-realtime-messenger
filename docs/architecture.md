# Архитектура ITMessage

Актуальная архитектура после PR #13 (4 ноября 2026). История исправлений — в [CHANGELOG](CHANGELOG.md), оставшиеся задачи — в [TODO](TODO.md). Подробные последовательности — в [data_flow.md](data_flow.md).

## 1. Компоненты и границы ответственности

```mermaid
flowchart LR
    B["Браузер<br/>HTML + ES Modules"] -->|HTTPS / REST| API["FastAPI<br/>routes"]
    B <-->|WebSocket| WS["WS endpoint<br/>конкретный воркер"]
    API --> S["Services<br/>бизнес-логика"]
    WS --> S
    S --> DAO["DAO / SQLAlchemy"]
    DAO --> PG[("PostgreSQL 16<br/>пользователи, чаты, сообщения, файлы")]
    S --> R[("Redis 7<br/>сессии, лимиты, presence")]
    S --> PUB["WS manager<br/>Redis Pub/Sub"]
    PUB <-->|"события"| R
    PUB --> WS
    S --> UP[("uploads_data<br/>файлы вне StaticFiles")]
```

* `routes/` — HTTP и WebSocket, валидация и управление транзакциями.
* `services/` — авторизация, чаты, сообщения, файлы, глобальный presence и WS-маршрутизация.
* `dao/`, `models/` — доступ к данным, SQLAlchemy и PostgreSQL.
* `schemas/` — Pydantic DTO; `exceptions/` — типизированные ошибки.
* `core/`, `features/`, `ui/` — клиентское состояние, сценарии и отображение.
* `app/main.py` — lifespan: Redis, подписчик WebSocket, shutdown соединений и пула БД.

## 2. Production-топология: четыре воркера

```mermaid
flowchart TB
    Browser["Браузеры и вкладки"] --> Port["Порт 8000 / Uvicorn master"]
    subgraph BACK["backend: UVICORN_WORKERS=4"]
        W1["Worker 1<br/>локальные сокеты"]
        W2["Worker 2<br/>локальные сокеты"]
        W3["Worker 3<br/>локальные сокеты"]
        W4["Worker 4<br/>локальные сокеты"]
    end
    Port --> W1 & W2 & W3 & W4
    W1 & W2 & W3 & W4 <-->|"publish / subscribe"| REDIS[("Redis Pub/Sub")]
    W1 & W2 & W3 & W4 <-->|"сессии / TTL presence / rate limit"| REDIS
    W1 & W2 & W3 & W4 --> DB[("PostgreSQL")]
    W1 & W2 & W3 & W4 --> FILES[("Docker volume: uploads_data")]
```

Соединение WebSocket принадлежит одному воркеру, а события Redis получают все подписчики и доставляют **только своим локальным вкладкам адресатов**. `WebSocketManager` использует `asyncio.Lock` для локального реестра соединений; глобальный статус отслеживает Redis (`ZSET`, TTL 90 секунд, атомарные Lua-операции). Счётчики rate limit также хранятся в Redis.

При обрыве Pub/Sub подписчик повторяет подключение. Redis Pub/Sub **не хранит** события на время отсутствия подписчика, поэтому база PostgreSQL остаётся источником истины, а клиент обновляет чаты и историю после WS reconnect. Это восстановление состояния, не гарантия доставки каждого push-события.

## 3. Реляционная модель

```mermaid
erDiagram
    USER ||--o{ MESSAGE : "sender_id"
    USER ||--o{ FILE : "owner_id"
    CHAT ||--o{ MESSAGE : "chat_id"
    MESSAGE o|--o| FILE : "message_file_id"
    USER {
        int id PK
        string username
        string email
        string hashed_password
        datetime last_seen_at
    }
    CHAT {
        int id PK
        int_array users "sorted pair of user ids"
        datetime created_at
    }
    MESSAGE {
        int id PK
        int chat_id FK
        int sender_id FK
        int message_file_id FK
        string message_text
        datetime sent_at
        boolean is_deleted
    }
    FILE {
        int id PK
        int owner_id FK
        string file_path
        string original_name
        string mime_type
        bigint size_bytes
    }
```

**Важно:** связь `USER ↔ CHAT` логическая, через `chats.users: ARRAY(Integer)`, а не внешний ключ или `jsonb`. Для прямого чата IDs сортируются; уникальный B-tree индекс по массиву не допускает два одинаковых канонических набора. Прямое сообщение и файл связаны опционально. Удаление сообщения — soft-delete, удаление чата удаляет зависимые записи; физическая очистка файлов выполняется после фиксации транзакции (с оговоркой об аварии между commit и cleanup).

## 4. Клиентские модули и события

```mermaid
flowchart LR
    APP["app.js<br/>bootstrap"] --> SOCKET["core/socket.js<br/>reconnect / ping-pong"]
    APP --> FEATURES["features/<br/>chats, messages, send, search"]
    APP --> STORE["core/store.js<br/>нормализованное состояние"]
    SOCKET --> HANDLER["core/wsHandler.js<br/>события сервера"]
    HANDLER --> STORE
    FEATURES --> API["core/api.js<br/>Axios + JWT refresh"]
    FEATURES --> STORE
    STORE --> UI["ui/<br/>messageView, imageLoader,<br/>wsStatus, lightbox"]
    LOGIN["login.js / register.js"] --> CSRF["core/csrf.js<br/>без зависимости от Axios"]
    API --> CSRF
```

Отправитель генерирует `client_id`, добавляет optimistic-сообщение в store, а затем подтверждает его по HTTP-ответу или `new_message` WebSocket. Вход и регистрация не зависят от инициализации Axios.

## 5. API

| Группа | Маршруты |
| --- | --- |
| Auth | `POST /api/auth/register`, `login`, `refresh`, `logout` |
| Users | `GET /api/users/me`, `search?query=`, `{user_id}` |
| Chats | `GET /api/chats`, `/direct/{target_id}`; `DELETE /api/chats/{chat_id}` |
| Messages | `GET /api/messages/{chat_id}`, `POST /api/messages/{chat_id}`, `DELETE /api/messages/{message_id}` |
| Files | `GET /api/files/{file_id}` (включая обработку изображений) |
| WebSocket | `/api/ws/{user_id}` с Origin и cookie-авторизацией |

HTTP-роуты доступны через FastAPI OpenAPI (`/docs`); cookies с JWT и CSRF используются для записи. WebSocket до соединения проверяет точное значение `Origin` по `ALLOWED_ORIGINS`.

## 6. Проверки и известные ограничения

Единый [workflow CI](../.github/workflows/ci.yml) содержит независимые jobs для Python (Ruff, mypy, unit, PostgreSQL миграции, Redis интеграция, HTTP smoke), Node.js и Docker Compose с четырьмя воркерами. Подробнее: [ci.md](ci.md), [ws-multiworker.md](ws-multiworker.md).

Действующие ограничения: временная потеря Pub/Sub событий при сбое Redis; возможная перестановка событий online/offline при быстром reconnect (N19); отсутствие durable очереди для гарантированной очистки файлов после аварийного завершения процесса. Детали и решения — в [TODO.md](TODO.md).
