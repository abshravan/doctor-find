.PHONY: help up down logs api-shell test lint fmt migrate seed

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Boot the full stack (db + redis + api)
	docker compose up --build

down: ## Stop and remove containers
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

api-shell: ## Shell into the API container
	docker compose exec api bash

test: ## Run backend tests
	cd apps/api && pytest -q

lint: ## Lint backend
	cd apps/api && ruff check . && mypy app

fmt: ## Format backend
	cd apps/api && ruff format . && ruff check --fix .

migrate: ## Run DB migrations
	cd apps/api && alembic upgrade head

seed: ## Seed sample doctors/clinics
	cd apps/api && python -m app.scripts.seed
