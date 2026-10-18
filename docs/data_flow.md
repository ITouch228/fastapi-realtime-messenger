# Data Flow ITMessage

> Как данные текут через систему. Каждая диаграмма — отдельный флоу.

---

## 1. Авторизация (вход)

> `features/login.js` и `features/register.js` идут через чистый `fetch`, минуя `core/api.js` —
> чтобы не тянуть интерсептор refresh там, где пользователь ещё не авторизован. `core/api.js`
> подключается только после входа (GET /users/me).
>
> `sub` токена = session_id, user_id резолвится через Redis → сессии отзываемые.

```mermaid
sequenceDiagram
    actor User
    participant Login as features/login.js (fetch)
    participant Route as routes/auth.py
    participant Svc as services/auth.py
    participant DAO as UserDAO
    participant Sec as utils/security.py
    participant SM as SessionManager (Redis)
    participant JWT as utils/jwt.py

    User->>Login: логин + пароль
    Login->>Route: POST /auth/login (без core/api.js)
    Route->>Svc: authenticate_user(user_data)
    Svc->>DAO: find_by_login (email|username)
    DAO-->>Svc: User | None
    alt юзер не найден или неактивен
        Svc->>Sec: verify_password(pw, DUMMY_HASH)
        Note right of Sec: защита от timing-атаки
        Svc-->>Route: UnauthorizedError → 401
    else найден
        Svc->>Sec: verify_password(pw, hashed)
        Svc-->>Route: UserInDB
    end
    Route->>Svc: create_session(user_id)
    Svc->>SM: create(user_id) → session_id
    Svc->>JWT: create_access_token + create_refresh_token
    Svc-->>Route: (access, refresh)
    Route-->>Login: set-cookie access + refresh + csrftoken
    Note over Login: location.href = /messages
```

---

## 1b. Проверка текущей сессии (после входа)

```mermaid
sequenceDiagram
    participant API as core/api.js
    participant Route as routes/users.py
    participant Svc as services/auth.py
    participant JWT as utils/jwt.py
    participant SM as SessionManager (Redis)
    participant UMGR as UserManager

    API->>Route: GET /users/me (cookie access)
    Route->>Svc: get_current_user
    Svc->>Svc: get_current_user_from_cookie
    Svc->>JWT: verify_token(access) → session_id
    Svc->>SM: get_user_id(session_id)
    SM-->>Svc: user_id | None
    Svc->>UMGR: get_active(user_id)
    UMGR-->>Svc: UserResponse | None
    Svc-->>Route: UserResponse
    Route-->>API: UserResponse
```

---

## 1c. Refresh токена (ротация сессии)

> ✅ Бизнес-логика в `AuthManager.rotate_session()` — роут только читает cookie
> и ставит новые. Ошибки токенов (JWTError/RedisError) → `AppError` в `_generate_tokens`.
> Фикс: при неактивном/удалённом пользователе старая сессия теперь отзывается.
> ✅ CSRF: POST /auth/refresh требует `X-CSRF-Token` header == кука `csrftoken`.

```mermaid
sequenceDiagram
    participant API as core/api.js
    participant Route as routes/auth.py
    participant Svc as AuthManager.rotate_session
    participant JWT as utils/jwt.py
    participant SM as SessionManager (Redis)
    participant UMGR as UserManager

    API->>Route: POST /auth/refresh (cookie refresh + X-CSRF-Token)
    Route->>Route: require_csrf (csrftoken cookie == header)
    Route->>Svc: rotate_session(refresh)
    Svc->>JWT: verify_token(refresh) → session_id
    Svc->>SM: get_user_id(session_id)
    Svc->>UMGR: get_active(user_id)
    alt не активен / не найден
        Svc->>SM: remove(session_id)
        Svc-->>Route: UnauthorizedError → 401
    end
    Svc->>SM: remove(old session_id)
    Svc->>SM: create(user_id) → new session_id
    Svc->>JWT: create_access_token + create_refresh_token
    Svc-->>Route: (access, refresh)
    Route-->>API: set-cookie access + refresh + csrftoken (rotated)
```

---

## 1d. Logout

> ✅ CSRF: POST /auth/logout требует `X-CSRF-Token` header == кука `csrftoken`.
> Отзывает сессию в Redis + чистит access/refresh/csrftoken куки.

```mermaid
sequenceDiagram
    participant API as core/api.js
    participant Route as routes/auth.py
    participant CSRF as require_csrf
    participant Svc as AuthManager.revoke_session
    participant JWT as utils/jwt.py
    participant SM as SessionManager (Redis)

    API->>Route: POST /auth/logout (cookie access + X-CSRF-Token)
    Route->>CSRF: require_csrf
    CSRF-->>Route: OK | PermissionDeniedError (403)
    Route->>Svc: revoke_session(access)
    Svc->>JWT: verify_token(access) → session_id
    Svc->>SM: remove(session_id)
    Route-->>API: 200, delete-cookie access + refresh + csrftoken
```

---

## 1e. Проблемы авторизации

```mermaid
graph LR
    subgraph WARN["🟢 Косметика (отложено, см. architecture.md §5)"]
        B4[trim дважды:<br/>схема + DAO (DUP1)]
        B5[Depends() внутри<br/>@staticmethod AuthManager (M8)]
    end

    subgraph OK["✅ Хорошо"]
        C1[authenticate_user<br/>в сервисе]
        C2[Timing-attack<br/>DUMMY_HASH]
        C3[Ротация сессий<br/>на refresh]
        C4[JWT sub =<br/>session_id]
        C5[UserResponse<br/>id возвращён]
        C6[лог auth.py<br/>user_data.login]
        C7[rotate_session /<br/>create_session /<br/>revoke_session<br/>в сервисе (W6)]
        C8[CSRF Double Submit<br/>cookie csrftoken +<br/>header X-CSRF-Token<br/>на logout/refresh/send/delete]
    end
```

---

## 2. Отправка сообщения

> ✅ Optimistic UI: клиент сразу кладёт сообщение в стор (`sended:false`, temp id)
> и рисует его. После успешного POST — `store.confirmMessage(response.data, clientId)`
> заменяет temp id на реальный и ставит `sended:true` (⏳ → ✓).
> Дубль `GET /messages` после отправки убран — список больше не перезагружается.
> ✅ CSRF: POST требует `X-CSRF-Token` == кука `csrftoken`.
> ✅ Unit of Work: create chat + create file + create message — 1 транзакция (`session.commit()`).
>
> ✅ W8: сервер шлёт `new_message` **всем** участникам, включая отправителя,
> а payload содержит `client_id`. `store.confirmMessage` идемпотентен: и POST-ответ,
> и WS-событие с одинаковым `client_id` приведут к одному подтверждению (без дублей).
> ✅ W9: матчинг оптимистичного сообщения — по `client_id` (uuid), не по тексту.

```mermaid
sequenceDiagram
    actor User
    participant Send as features/send.js
    participant Store as core/store.js
    participant View as ui/messageView.js
    participant API as core/api.js
    participant Msg as routes/messages.py
    participant Mgr as MessageManager
    participant DB as PostgreSQL
    participant WSM as WebSocketManager
    actor Peer as Собеседник

    User->>Send: Ввод + Enter
    Send->>Store: addOptimisticMessage (sended:false, temp id)
    Store-->>View: notify message:new → appendMessage (⏳)
    Send->>API: POST /messages/chatId (FormData + X-CSRF-Token)
    API->>API: require_csrf (csrftoken cookie == header)
    alt temp-chat
        API->>API: ChatManager.create
    end
    API->>Mgr: MessageManager.create
    Mgr->>DB: MessageDAO.add
    Mgr-->>API: MessageInDb → MessageResponse
    API->>DB: session.commit()
    API->>WSM: send_personal_message (всем участникам, + client_id)
    WSM-->>Peer: WS push new_message
    WSM-->>Send: WS push new_message (отправителю, + client_id)
    API-->>Send: MessageResponse (+ client_id)
    Send->>Store: confirmMessage (sended:true, real id)
    Store-->>View: notify message:update → updateMessageInDom (✓)
    Note over Send: confirmMessage идемпотентен:<br/>POST-ответ и WS → одно подтверждение
    Note over Send: temp-chat: replaceTempChat(tempId, realId)
```

---

## 2b. Загрузка сообщений чата

> ✅ W2: чат и его сообщения — одним запросом
> (`MessageDAO.find_by_chat_with_chat`, outerjoin). Проверка доступа к чату
> делается по `chat.users` из того же запроса — без второго round-trip.
> ✅ Файлы сообщений подтягиваются батчем (`FileDAO.find_by_ids`) — нет N+1.

```mermaid
sequenceDiagram
    participant Msg as features/messages.js
    participant API as core/api.js
    participant Route as routes/messages.py
    participant Mgr as MessageManager
    participant DAO as MessageDAO
    participant FDAO as FileDAO
    participant DB as PostgreSQL

    Msg->>API: GET /messages/chatId
    API->>Route: get_chat_messages
    Route->>Mgr: get_chat_messages(chat_id, user_id)
    Mgr->>DAO: find_by_chat_with_chat(chat_id)
    DAO->>DB: SELECT chat + messages (outerjoin, 1 запрос)
    DAO-->>Mgr: [(chat, message | None)]
    alt чат не найден
        Mgr-->>Route: NotFoundError → 404
    else user не в chat.users
        Mgr-->>Route: PermissionDeniedError → 403
    end
    Mgr->>FDAO: find_by_ids(file_ids)
    FDAO->>DB: SELECT files WHERE id IN (...) (1 запрос)
    FDAO-->>Mgr: files
    Mgr-->>Route: list[MessageResponse]
    Route-->>API: 200
```

---

## 3. Realtime-получение сообщения

> ✅ Стор обновляется всегда: активный чат → `confirmMessage` (render одного
> сообщения), неактивный → `updateChatLastMessage` + `invalidateMessages`
> (история подтянется с сервера при открытии).
> ✅ W8: событие приходит и отправителю (payload с `client_id`) — подтверждение
> оптимистичного сообщения не зависит от POST-ответа.

```mermaid
sequenceDiagram
    actor Sender
    participant API as routes/messages.py
    participant WSM as WebSocketManager
    participant WS as core/socket.js
    participant H as core/wsHandler.js
    participant Store as core/store.js
    participant DOM as DOM

    Sender->>API: POST /messages
    API->>WSM: send_personal_message (всем участникам)
    WSM-->>WS: push new_message (и отправителю)
    WS->>H: handleWebSocketMessage
    alt чат активен
        H->>Store: confirmMessage(msg, client_id)
        Store->>DOM: updateMessageInDom / appendMessage
    else чат неактивен
        H->>Store: updateChatLastMessage + invalidateMessages
        Store->>DOM: notify chatList (last_message)
    end
    H->>DOM: NotifySound.play (если не активен)
```

---

## 4. Создание temp-чата

> ✅ temp-чат использует `peer_id` в FormData вместо парсинга строки.
> `store.replaceTempChat(tempId, realId)` атомарно переносит чат, сообщения и DOM-узел.

```mermaid
sequenceDiagram
    actor User
    participant Chats as features/chats.js
    participant Store as core/store.js
    participant API as core/api.js
    participant Route as routes/messages.py
    participant Mgr as ChatManager
    participant WS as WebSocketManager
    actor Peer as Собеседник

    User->>Chats: клик на пользователя
    Chats->>API: GET /chats/direct/targetId
    API-->>Chats: chat | None
    alt чата нет
        Chats->>Store: addChat(id: temp-targetId)
    else чат есть
        Chats->>Chats: click существующего
    end
    User->>Chats: ввод + Enter
    Chats->>Store: addOptimisticMessage(temp-targetId)
    Chats->>API: POST /messages/temp-targetId (FormData + peer_id)
    API->>Route: send_message(chat_id, peer_id)
    Route->>Mgr: ChatManager.create(current_user.id, peer_id)
    Mgr-->>Route: ChatInDb (real_id)
    Route->>WS: new_chat → peer + self
    WS-->>Peer: push new_chat
    Route-->>API: MessageResponse (chat_id = real_id)
    API-->>Chats: response
    Chats->>Store: replaceTempChat(temp-targetId, real_id)
    Note over Store: чат + сообщения + DOM-узел на реальном ID
```

---

## 5. Удаление сообщения

> ✅ CSRF: DELETE требует `X-CSRF-Token` == кука `csrftoken`.
> ✅ W3: сообщение + участники чата — одним запросом
> (`MessageDAO.find_with_chat_users`, join). Проверки автора и членства — в Python.
> ✅ Unit of Work: `session.commit()` только после write-операции.

```mermaid
sequenceDiagram
    actor User
    participant Msg as messages.js
    participant API as core/api.js
    participant Route as routes/messages.py
    participant CSRF as require_csrf
    participant Mgr as MessageManager
    participant DAO as MessageDAO
    participant DB as PostgreSQL
    participant Store as core/store.js
    participant DOM as DOM

    User->>Msg: клик на кнопку удаления
    Msg->>API: DELETE /messages/messageId (X-CSRF-Token)
    API->>Route: DELETE
    Route->>CSRF: require_csrf
    CSRF-->>Route: OK | 403
    Route->>Mgr: delete(message_id, user_id)
    Mgr->>DAO: find_with_chat_users(message_id)
    DAO->>DB: SELECT message + chat.users (join, 1 запрос)
    DAO-->>Mgr: (message, chat_users)
    alt message не найден
        Mgr-->>Route: NotFoundError → 404
    else не автор / не в чате
        Mgr-->>Route: PermissionDeniedError → 403
    end
    Mgr->>DAO: soft_delete_message(message_id)
    Route->>DB: session.commit()
    Route-->>API: 204 No Content
    Msg->>Store: softDeleteMessage
    Store->>DOM: notify message:update → «Удалено»
```

---

## 6. Обработка 401 (auto-refresh)

> ✅ B3 (исправлено): в обработчике 401 использовалась неопределённая переменная
> `url` (ReferenceError) — авто-refresh падал. Теперь проверка идёт по `original.url`.

```mermaid
sequenceDiagram
    participant Comp as компонент
    participant API as core/api.js
    participant Auth as api.js refresh
    participant B as Backend

    Comp->>API: GET /chats
    API->>B: GET /chats (cookie: access)
    B-->>API: 401 Unauthorized
    API->>Auth: refreshPromise
    Auth->>B: POST /auth/refresh (cookie: refresh)
    B-->>Auth: access_token
    Auth-->>API: new access_token
    API->>B: GET /chats (retry)
    B-->>API: 200 OK
    API-->>Comp: ChatResponse array
```

---

## 7. Жизненный цикл WebSocket

```mermaid
stateDiagram-v2
    [*] --> Connecting: DOMContentLoaded
    Connecting --> Open: onopen
    Connecting --> Closed: 4401/4404 auth fail
    Open --> Open: onmessage
    Open --> Reconnecting: onclose (не auth)
    Open --> Closed: onclose (4401/4404)
    Reconnecting --> Open: reconnect OK
    Reconnecting --> Reconnecting: backoff (1s→2s→4s→...→30s)
    Reconnecting --> Disconnected: > 10 попыток
    Disconnected --> [*]
    Open --> Closed: beforeunload (intentional)

    note right of Reconnecting: ✅ exponential backoff\n✅ статус на UI
    note right of Closed: ✅ индикатор статуса
```

---

## 8. Состояния чатов

```mermaid
stateDiagram-v2
    [*] --> NoChats: нет чатов
    [*] --> ActiveChat: есть чаты, клик

    NoChats --> TempChat: startNewChat
    TempChat --> ActiveChat: отправить сообщение
    TempChat --> NoChats: отмена

    ActiveChat --> ActiveChat: переключение чатов
    ActiveChat --> NoChats: удалить чат
```

---

## 9. Состояние отправки (optimistic)

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Optimistic: Enter → addOptimisticMessage (⏳ sended:false, client_id)
    Optimistic --> Locked: isSending=true, POST /messages
    Locked --> Confirmed: POST OK → confirmMessage (✓ sended:true)
    Locked --> Confirmed: WS new_message (client_id) → confirmMessage (✓)
    Locked --> Failed: error → alert
    Confirmed --> Idle: unlock
    Failed --> Idle: unlock (сообщение остаётся ⏳ до повторной отправки)
```

> ✅ W8/W9: подтверждение может прийти как из POST-ответа, так и из WS-события
> (сервер шлёт `new_message` и отправителю). `confirmMessage` идемпотентен по
> `client_id`/реальному id — двойное подтверждение не создаёт дубль.

---

## Сводка по флоу

| Флоу | Статус | Проблема |
|------|--------|----------|
| Авторизация (вход) | ✅ | — |
| Проверка сессии | ✅ | — |
| Refresh токена | ✅ | Бизнес-логика в AuthManager.rotate_session, CSRF |
| Logout | ✅ | CSRF Double Submit Cookie |
| Отправка | ✅ | Optimistic + confirm по client_id (POST/WS) + CSRF + Unit of Work |
| Загрузка сообщений | ✅ | W2: chat+messages одним запросом, файлы батчем (нет N+1) |
| Отправка — типы | ✅ | 10/10 несоотв. типов исправлены (см. architecture.md §6) |
| Realtime | ✅ | W8: событие и отправителю; активный: confirmMessage → render; неактивный: invalidate + chatList |
| Temp-чат | ✅ | peer_id в FormData, store.replaceTempChat, без split |
| Удаление сообщения | ✅ | W3: message+chat одним запросом, CSRF + Unit of Work |
| Auto-refresh | ✅ | B3: url → original.url (был ReferenceError) |
| WebSocket | ✅ | Reconnect + индикатор статуса |
| Загрузка файла | ✅ | Pillow-рендер и лог вынесены в utils.render_image_response |
| Хранение файлов | ✅ | uploads в `BASE_DIR/uploads`, вне STATIC_DIR |
| get_redis | ✅ | Double-checked locking с asyncio.Lock |
| session.commit | ✅ | Unit of Work — только на write-операциях |
| model_validate(None) | ✅ | `is None` до валидации |
| Нарушение слоёв | ✅ | Все DAO через сервисы (MessageManager/FileManager) |
| Состояния чатов | ✅ | — |
| Состояние отправки | ✅ | Optimistic (⏳→✓ через confirmMessage по client_id) |
| Открытие чата (offline) | ✅ | B2: рендер из стора сразу, без очистки до ответа сети |

## Принципы логирования

```
Route:   только HTTP-обвязка, логи почти не нужны
Service: все info/warning/error бизнес-событий
Access:  авто (uvicorn пишет сам: метод/путь/статус/время)
```

### Что перенести в сервисы

| Файл | Лог | Куда перенести | Статус |
|------|-----|----------------|--------|
| routes/auth.py | info регистрация | services/auth.py | ✅ в сервисе |
| routes/auth.py | except IntegrityError | — | ✅ убран (мёртвый, сервис кидает ConflictError) |
| routes/auth.py | login success/fail | services/auth.py | ✅ перенесено в authenticate_user |
| routes/auth.py | refresh/token errors | services/auth.py | ✅ rotate_session/_generate_tokens (B1 закрыто) |
| routes/messages.py | info temp-chat | ChatManager | ✅ убран (дубль ChatManager.create) |
| routes/messages.py | except Exception | AppError | ✅ все HTTPException → typed exceptions |
| routes/files.py | Pillow error | utils/files.render_image_response | ✅ перенесено в utils |

### Мёртвые импорты logger

- `routes/chats.py` — ✅ `get_logger`/`logger` удалены (был мёртвым)
- `routes/files.py` — ✅ `logger` удалён вместе с Pillow-логикой (ушла в utils)
- `routes/messages.py` — `logger` живой: fallback `except Exception` в `send_message`
- `services/*` — живой, бизнес-события
