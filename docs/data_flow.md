# Потоки данных ITMessage

Актуально после PR #13. Схема компонентов и модели данных — [architecture.md](architecture.md); проверка четырёх воркеров — [ws-multiworker.md](ws-multiworker.md).

## 1. Регистрация, вход и сессия

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant B as Браузер
    participant API as FastAPI Auth
    participant DB as PostgreSQL
    participant R as Redis
    U->>B: Отправка формы
    B->>API: POST /api/auth/register
    API->>DB: Проверка и создание пользователя
    DB-->>API: id
    API-->>B: 201
    B->>API: POST /api/auth/login
    API->>DB: Поиск и проверка пароля
    API->>R: Сессия с TTL
    R-->>API: OK
    API-->>B: Cookies access, refresh, csrftoken
    B->>API: GET /api/users/me + access cookie
    API->>R: Проверка session_id
    API-->>B: UserResponse
```

JWT подписывается RS256; access/refresh хранятся в HttpOnly cookies, `csrftoken` доступен JavaScript для заголовка `X-CSRF-Token`. Страницы входа и регистрации используют независимый `core/csrf.js`, без импорта Axios.

## 2. Ротация токена

```mermaid
sequenceDiagram
    participant B as Axios API
    participant A as Auth API
    participant R as Redis sessions
    B->>A: Запрос с истёкшим access
    A-->>B: 401
    B->>A: POST /api/auth/refresh + CSRF
    A->>R: Проверка refresh/session
    R-->>A: Действительная сессия
    A->>R: Отзыв старой и создание новой сессии
    A-->>B: Новые cookies
    B->>A: Повтор исходного запроса
    A-->>B: Ответ
```

В `core/api.js` параллельные запросы ожидают один выполняющийся refresh; повторный запрос инициируется только после получения новых cookies.

## 3. Отправка сообщения между четырьмя воркерами

```mermaid
sequenceDiagram
    actor A as Отправитель
    participant C as Frontend / store
    participant H as HTTP worker
    participant PG as PostgreSQL
    participant R as Redis Pub/Sub
    participant W as WS worker
    actor B as Получатель
    A->>C: Отправка текста или файла
    C->>C: Optimistic message (client_id)
    C->>H: POST /api/messages/{chat_id} (CSRF)
    H->>PG: Сохранение чата/сообщения/метаданных
    PG-->>H: Commit
    H->>R: publish(new_message, users, client_id)
    R-->>W: Событие подписчикам всех воркеров
    W-->>B: WebSocket new_message
    W-->>A: WebSocket new_message
    H-->>C: HTTP 201 MessageResponse
    C->>C: Confirm по client_id (без дубликата)
```

Физические файлы записываются в `uploads_data` вне публичной статики. При новом диалоге фронтенд передаёт `peer_id` и временный chat-id; API создаёт канонический чат в транзакции. `new_chat` и `new_message` публикуются после успешного commit.

**Ограничение:** Redis Pub/Sub не является durable очередью. Если после commit Redis недоступен, сообщение остаётся в PostgreSQL, но push может потеряться. Сбой публикации не должен превращать успешный commit в ложную ошибку повторной отправки.

## 4. Отключение Redis и переподключение

```mermaid
sequenceDiagram
    participant R as Redis
    participant S as Worker Pub/Sub task
    participant B as Браузер
    participant API as REST API
    participant PG as PostgreSQL
    R--xS: Обрыв Pub/Sub
    S->>S: Логирование + повтор subscribe
    loop Пока Redis недоступен
        S->>R: Повторная подписка
        R--xS: Сбой
    end
    S->>R: Успешный subscribe
    R-->>S: Новые push события
    B->>B: WS reconnect с backoff
    B->>API: GET /api/chats
    B->>API: GET /api/messages/{chat_id}
    API->>PG: Текущее состояние
    PG-->>API: Подтверждённые записи
    API-->>B: Актуальная история
```

В PR #13 обработаны ошибки повторной подписки Redis и очистки WS-подключений. Обработчик WS закрывает соединение с кодом 1012 при недоступности Redis в heartbeat, после чего клиент может восстановить соединение. События за время разрыва **не воспроизводятся из Pub/Sub**; история восстанавливается только по REST.

## 5. Онлайн-статус и несколько вкладок

```mermaid
flowchart TD
    A["WS accepted"] --> B["Redis join(user_id, connection_token)"]
    B --> C{"Первая активная аренда?"}
    C -->|Да| D["notify_online"]
    C -->|Нет| E["Пользователь уже online"]
    D --> F["Heartbeat -> refresh TTL"]
    E --> F
    F --> G{"Соединение закрыто?"}
    G -->|Нет| F
    G -->|Да| H["Redis leave(token)"]
    H --> I{"Последняя аренда?"}
    I -->|Да| J["last_seen commit -> notify_offline"]
    I -->|Нет| K["Остальные вкладки online"]
```

Redis хранит отдельную аренду каждой вкладки в ZSET, индекс пользователей и TTL. При аварийной остановке воркера статус истечёт, но мгновенное push-уведомление по TTL не гарантировано. Быстрый reconnect может переупорядочить `presence_update` — открытая задача N19.

## 6. Удаление файлов и сообщения

```mermaid
sequenceDiagram
    participant C as Клиент
    participant API as FastAPI
    participant DB as PostgreSQL
    participant FS as uploads_data
    C->>API: DELETE /api/chats/{chat_id} + CSRF
    API->>DB: Удаление записей и получение путей
    API->>DB: Commit
    DB-->>API: OK
    API->>FS: Очистка физических файлов
    API-->>C: 204
```

Очистка файлов после commit предотвращает потерю содержимого при неудачной транзакции. Но при аварии между commit и удалением файла возможны осиротевшие файлы — нужна отдельная durable cleanup queue/outbox. Удаление сообщения — soft-delete без немедленного удаления всех связанных физических файлов.
