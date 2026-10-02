.PHONY: help build up down down-v restart logs
.PHONY: migrate lint lint-fix format check quality

# ========================================
# DOCKER COMMANDS
# ========================================

build:
	docker-compose up --build

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
# LINTING & CODE QUALITY (ruff + mypy)
# ========================================

lint:
	@echo "Ruff (lint)..."
	cd backend && ruff check .
	@echo "Ruff (format)..."
	cd backend && ruff format --check .
	@echo "Mypy..."
	cd backend && mypy --package app

lint-fix:
	cd backend && ruff check --fix .
	cd backend && ruff format .

format:
	cd backend && ruff check --fix .
	cd backend && ruff format .

# ========================================
# QUALITY REPORT (ruff + mypy with logs)
# ========================================

quality:
	cd backend && python tools/quality.py

# ========================================
# HELP (default)
# ========================================

help:
	@echo "Available commands:"
	@echo ""
	@echo "DOCKER:"
	@echo "  build          Build and run containers (with logs)"
	@echo "  up             Run containers in background"
	@echo "  down           Stop containers"
	@echo "  down-v         Stop containers and remove volumes"
	@echo "  restart        Restart containers"
	@echo "  logs           Show container logs"
	@echo ""
	@echo "ALEMBIC:"
	@echo "  migrate        Apply migrations"
	@echo ""
	@echo "LINTING:"
	@echo "  lint           Run all linters (ruff + mypy)"
	@echo "  lint-fix       Auto-fix errors"
	@echo "  format         Format all code"
	@echo ""
	@echo "QUALITY:"
	@echo "  quality        Full quality report with logs"

.DEFAULT_GOAL := help
