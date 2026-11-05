# Стратегия тестирования ITMessage

Версия тестовых контрактов после PR #20. Цель — все изменения в мессенджере проверять автоматическими тестами на трёх уровнях: unit, integration и end-to-end. Никаких внешних production-ресурсов в CI.

## Уровни и источники истины

| Уровень | Что проверяет | Зависимости | Запуск |
| --- | --- | --- | --- |
| **Unit** | Валидация, генерация токенов, бизнес-логика, ошибки, обработка событий, алгоритмы | Fake/mocks, временные каталоги | `coverage run ... unittest` |
| **Integration Redis** | Pub/Sub, presence, версии событий, несколько процессов | Отдельная Redis 7 DB 15 | `REDIS_INTEGRATION_TESTS=1 python -m unittest discover ... test_integration_*.py` |
| **Integration PostgreSQL** | Alembic baseline, структура и ограничения БД | Одноразовая PostgreSQL 16 | `alembic upgrade head && alembic check` |
| **HTTP contracts** | Реальные status codes, cookies, CSRF, авторизация, чужие чаты, JSON/OpenAPI | FastAPI + PostgreSQL + Redis + RSA | `python tests/contracts_http.py` |
| **Compose smoke** | Реальный образ, четыре Uvicorn-воркера, RSA и HTTP после рестарта | Docker Compose | CI job `docker_compose` |
| **Browser E2E** | Пользовательские действия, DOM, WebSocket, несколько вкладок, файлы | Playwright + изолированный Compose | Следующий этап, в текущем PR не введён |

Условие классификации: тест с сетью, настоящей БД, Redis или живым сервером — **integration/contract**, не unit, даже если написан на `unittest`. `backend/tests/smoke_http.py` остаётся быстрым smoke-сценарием, а `contracts_http.py` — проверкой конкретных условий API.

## HTTP-контракты (исполняемые)

В `backend/tests/contracts_http.py` проверяются:

| Контракт | Ожидаемое поведение |
| --- | --- |
| `GET /api/users/me` без сессии | 401 + JSON `detail` |
| `GET /api/chats` и `GET /api/messages/{id}` без сессии | 401 |
| `POST /api/auth/register` с валидными данными | 201 |
| `POST /api/auth/login` с CSRF заголовком | 200 и действительная авторизация |
| `POST /api/auth/logout` без CSRF или с неверным токеном | 403; пользователь остаётся в системе |
| `POST /api/messages/{temp_id}` в новый direct-чат | 201; `id`, `chat_id`, `sender_id`, `message_text` |
| `GET /api/messages/{chat_id}` участником | 200 и сохранённое сообщение |
| `GET /api/messages/{chat_id}` посторонним | 403 |
| `DELETE /api/chats/{chat_id}` посторонним | 403 |
| `GET /openapi.json` | OpenAPI 3 и необходимые пути/HTTP методы |

Контрактные тесты создают три уникальные учётные записи, работают через отдельные cookie jars и проверяют реальный FastAPI. Запускайте их **только на тестовой инфраструктуре**: тесты пишут данные в БД.

## Отчёт покрытия

`coverage.py` измеряет **branch coverage** на unit-тестах и сохраняет `backend/coverage.xml` артефактом CI `backend-unit-coverage`. В первой итерации фиксируем фактический baseline; не ставим произвольный порог без измерения.

После нескольких PR по покрытиям вводим `fail-under` не ниже достигнутого baseline и поднимаем постепенно. Целевые ориентиры перед релизом: 80%+ line coverage бизнес-логики, 70%+ branch coverage, обязательные регрессии на критических путях; проценты — **цель, а не текущая метрика**. Одной цифры недостаточно: авторизация, ACL файлов, целостность транзакций, Redis failure/recovery и reconnect должны быть покрыты отдельными контрактными сценариями.

## Команды для разработчика

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend

# Unit (без внешних инфраструктурных сервисов)
coverage run --branch --source=app -m unittest discover -s tests -p 'test_*.py' -v
coverage report --show-missing
coverage html

# Redis integration — только отдельная локальная тестовая БД Redis!
REDIS_INTEGRATION_TESTS=1 REDIS_INTEGRATION_URL=redis://localhost:6379/15 \
    python -m unittest discover -s tests -p 'test_integration_*.py' -v

# PostgreSQL schema (только на новой пустой БД)
alembic upgrade head
alembic check

# HTTP contract после запуска FastAPI на тестовой БД
python tests/contracts_http.py
```

В PowerShell переменные окружения задаются через `$env:NAME = 'value'`; синтаксис однострочного запуска с `NAME=value` относится к Unix-shell.

## Правила CI

1. Ruff lint, Ruff format, mypy и unit-тесты обязательны.
2. Redis integration и HTTP contracts обязательны (не допускается замена моками).
3. Alembic schema check обязателен для свежей PostgreSQL.
4. Docker Compose с четырьмя воркерами и HTTP smoke обязателен.
5. Browser E2E станет required check, когда появится стабильный Playwright-контур.
6. Никаких секретов production, `flushdb` на общей Redis или `downgrade base` на реальной БД.

## Порядок расширения

- Контракты сессий: refresh/logout/revocation, истёкший токен, SameSite/Secure.
- PostgreSQL/Redis: реальные конкурентные транзакции, rollback, outbox/retry и миграции.
- WebSocket: авторизация Origin/ACL, reconnect, четыре воркера, порядок presence и пропущенные push.
- Playwright E2E: регистрация → чат → сообщения, несколько вкладок, файлы, удаления, восстановление сессии.
- Надёжность CI: воспроизводимость, отсутствие flaky тестов, артефакты логов при падении.

Каждое исправление функциональности должно сопровождаться тестом, воспроизводящим исходную проблему.
