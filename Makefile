.PHONY: dev migrate test lint fmt clean

dev:
	docker compose up

migrate:
	cd backend && uv run alembic upgrade head

test:
	cd backend && uv run pytest -q
	cd frontend && pnpm vitest run

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy src
	cd frontend && pnpm exec tsc --noEmit

fmt:
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .

clean:
	docker compose down -v
