.PHONY: help build up down down-v restart logs
.PHONY: migrate lint lint-front lint-back lint-fix format format-front format-back check quality

# ========================================
# DOCKER COMMANDS
# ========================================

build:
	docker-compose up --build

build-d:
	docker-compose up -d --build

up:
	docker-compose up -d

down:
	docker-compose down

down-v:
	docker-compose down -v

restart: down up

logs:
	docker-compose logs -f

# ========================================
# ALEMBIC (run via docker-compose exec)
# ========================================

migrate:
	docker-compose exec backend alembic upgrade head

# ========================================
# LINTING & CODE QUALITY (ruff + mypy + eslint + prettier)
# ========================================

lint-back:
	@echo "Ruff (lint)..."
	cd backend && ruff check .
	@echo "Ruff (format check)..."
	cd backend && ruff format --check .
	@echo "Mypy..."
	cd backend && mypy --package app

lint-front:
	@echo "ESLint..."
	npx eslint backend/app/static/js
	@echo "Prettier (check)..."
	npx prettier --check "backend/app/static/**/*.{js,css,html}"

lint: lint-back lint-front

lint-fix:
	@echo "Ruff check --fix..."
	cd backend && ruff check --fix .
	@echo "Ruff format..."
	cd backend && ruff format .
	@echo "ESLint --fix..."
	npx eslint --fix backend/app/static/js
	@echo "Prettier --write..."
	npx prettier --write "backend/app/static/**/*.{js,css,html}"

# ========================================
# FORMATTING
# ========================================

format-back:
	cd backend && ruff check --fix .
	cd backend && ruff format .

format-front:
	npx prettier --write "backend/app/static/**/*.{js,css,html}"

format: format-back format-front

# ========================================
# QUALITY (формат + проверка)
# ========================================

check: format lint

quality: check
	@echo "All checks passed."