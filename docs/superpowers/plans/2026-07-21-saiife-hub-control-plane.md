# saiife-hub Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build saiife-hub — the public, customer-facing control plane that owns identity, Stripe subscriptions, saiife-cloud tenant lifecycle, and the `sfc_` account tokens a desktop install pastes to reach the webhook relay.

**Architecture:** A Next.js 16 frontend (`frontend/`) that renders and calls a FastAPI backend (`backend/`) over cookie-authenticated JSON; every computation — argon2id hashing, JWT minting, CSRF, Stripe signature verification, scrypt account-token hashing, cloud tenant lifecycle — lives in the backend, and the frontend holds no business logic. All saiife-cloud interaction goes through one `CloudControlPlane` seam with an in-memory mock (what every test runs against) and a deferred HTTP implementation that raises `NotWiredError` until saiife-cloud implements the admin API this repo specifies. A shared brand layer lives in `packages/ui/`, and Terraform in `infra/` is authored but never applied.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · uv · pytest · argon2-cffi · PyJWT · py_webauthn · slowapi · structlog · Stripe (behind a seam) · Next.js 16 · React 19 · Tailwind v4 · pnpm · Vitest · Playwright · Terraform.

## Global Constraints

- Python `>=3.12,<3.13`; dependencies managed by `uv`; `package = false` (src layout, `PYTHONPATH=/app/src`).
- Node `22`; pnpm `9.12.3`; Next.js `16.2.6`; React `19.2.4`; Tailwind `^4`; TypeScript `^5`.
- Everything computational lives in the FastAPI backend. `frontend/` is UI only — no hashing, no token minting, no signature verification, no cloud calls.
- Account token format is pinned by saiife-cloud and must match byte-for-byte: `sfc_<tenantLookupId>_<secret>`, `ACCOUNT_TOKEN_PREFIX = "sfc_"`, `tenantLookupId` = 9 random bytes as 18 lowercase hex chars, `secret` = 32 random bytes base64url without padding.
- Account token hashing is pinned by saiife-cloud: scrypt with `N=16384, r=8, p=1, dklen=32`, 16-byte salt, password = `f"{pepper}:{secret}"` UTF-8, stored as `scrypt$16384$8$1$<saltBase64>$<hashBase64>`, constant-time compare, dummy-hash timing equalization on unknown-lookup-id.
- Account token secrets are stored hashed only, never logged, never returned after the single creation response.
- Stripe webhooks are signature-verified before any state change, and handlers are idempotent — a replayed `event.id` performs zero side effects.
- Auth flows keep argon2id (`m=65536, t=3, p=1`), CSRF double-submit protection, and refresh-token replay lockdown intact.
- Byte-identical responses on unknown-account lookups — no enumeration oracle (`/resend-verification` always returns `{"ok": true}`; account-token verification always fails with the same shape).
- Rate limiting on auth and token endpoints via slowapi.
- Secrets come from Secret Manager at runtime; never committed.
- This repo is **public**: no real GCP project IDs, no real endpoints, no pepper values, and no Stripe keys in committed config. Terraform vars that name real infrastructure have **no default** and must be supplied via `TF_VAR_*`.
- Everything must build and test with **no GCP account and no network**: all tests run against `InMemoryCloudControlPlane`, `MockStripeGateway`, and a local SQLite database.
- Do **not** use the word "provision" for tenant creation — saiife-cloud already uses `SubscriptionProvisioner` for Pub/Sub subscription provisioning. Use `create_tenant` / `delete_tenant`.
- Terraform in `infra/` is authored, never applied. No task runs `terraform apply`.

---

## File Structure

### Repository root

| Path | Single responsibility |
|---|---|
| `package.json` | pnpm workspace root scripts (`build`, `lint`, `test`, `e2e`). |
| `pnpm-workspace.yaml` | Declares `frontend` and `packages/*` as workspaces. |
| `.gitignore` | Ignores `node_modules`, `.next`, `.venv`, `__pycache__`, `*.db`, `.env`. |
| `.nvmrc` | Pins Node 22. |
| `Makefile` | `dev`, `migrate`, `test`, `lint`, `fmt`, `clean` entry points. |
| `docker-compose.yml` | Local Postgres + backend + frontend for manual dev. |
| `cloudbuild.yaml` | Builds and pushes the two container images. |
| `scripts/check-layout.sh` | Asserts the required top-level files exist. |
| `docs/2026-07-21-saiife-cloud-admin-api-contract.md` | The admin-API contract saiife-cloud must implement (deliverable). |

### `backend/`

| Path | Single responsibility |
|---|---|
| `pyproject.toml` | Dependencies, ruff/mypy/pytest configuration. |
| `alembic.ini` | Alembic script location and file template. |
| `alembic/env.py` | Async Alembic runner bound to `Base.metadata`. |
| `alembic/versions/20260721_1200_initial_auth.py` | Creates users, sessions, oauth_accounts, email_verifications, passkeys, passkey_challenges, auth_events. |
| `alembic/versions/20260721_1300_billing_tenants_installs.py` | Creates subscriptions, stripe_events, tenants, installs. |
| `Dockerfile` | Production image (uv build stage + slim runtime). |
| `Dockerfile.dev` | Local dev image with reload. |
| `.env.example` | Fake-valued env template; documents every setting. |
| `src/app/main.py` | App boot, middleware, error taxonomy, router registration. |
| `src/app/core/config.py` | Pydantic `Settings` — the only place env vars are read. |
| `src/app/core/logging.py` | structlog JSON logging configuration. |
| `src/app/core/rate_limit.py` | The shared slowapi `Limiter`. |
| `src/app/db/base.py` | SQLAlchemy `DeclarativeBase`. |
| `src/app/db/session.py` | Async engine, sessionmaker, `get_db` dependency. |
| `src/app/models/user.py` | User, Session, OAuthAccount, EmailVerification, Passkey, PasskeyChallenge, AuthEvent. |
| `src/app/models/billing.py` | Subscription, StripeEvent. |
| `src/app/models/tenant.py` | Tenant (the hub-side record of a saiife-cloud tenant). |
| `src/app/models/install.py` | Install (a desktop install linked to an account). |
| `src/app/mailer.py` | `ConsoleMailer` / `MailgunMailer` + `get_mailer`/`set_mailer` seam. |
| `src/app/auth/password.py` | argon2id hash / verify / needs_rehash. |
| `src/app/auth/jwt.py` | Access & refresh JWT issuance and verification. |
| `src/app/auth/cookies.py` | Session cookie names, set, clear. |
| `src/app/auth/csrf.py` | Double-submit CSRF middleware and its exemption list. |
| `src/app/auth/deps.py` | `current_user` / `verified_user` FastAPI dependencies. |
| `src/app/auth/schemas.py` | Pydantic request/response models for auth. |
| `src/app/auth/audit.py` | Writes `AuthEvent` rows. |
| `src/app/auth/oauth_google.py` | Google OAuth client build, code exchange, account-match classification. |
| `src/app/auth/passkeys.py` | py_webauthn option generation, verification, clone detection. |
| `src/app/api/v1/health/router.py` | `GET /api/v1/health`. |
| `src/app/api/v1/auth/router.py` | Every `/api/v1/auth/*` endpoint. |
| `src/app/cloud/errors.py` | `NotWiredError`. |
| `src/app/cloud/contracts.py` | Wire dataclasses for the cloud admin API. |
| `src/app/cloud/seam.py` | The `CloudControlPlane` protocol. |
| `src/app/cloud/mock.py` | `InMemoryCloudControlPlane` — what all tests run against. |
| `src/app/cloud/http.py` | `HttpCloudControlPlane` — deferred, raises `NotWiredError`. |
| `src/app/cloud/deps.py` | `get_cloud` / `set_cloud` selection seam. |
| `src/app/tenants/tokens.py` | `sfc_` token mint/parse and scrypt hash/verify. |
| `src/app/tenants/service.py` | `ensure_tenant`, `issue_account_token`, `remove_tenant`. |
| `src/app/tenants/routes.py` | `/api/v1/tenants/*`. |
| `src/app/billing/signature.py` | Stripe webhook signature verification. |
| `src/app/billing/gateway.py` | `StripeGateway` protocol + mock + HTTP implementation. |
| `src/app/billing/service.py` | Subscription state transitions driven by Stripe events. |
| `src/app/billing/routes.py` | `/api/v1/billing/*` including the webhook. |
| `src/app/installs/routes.py` | `/api/v1/installs/*` including cloud proxies. |
| `tests/conftest.py` | Env setup, sys.path, sqlite database, client and seam fixtures. |
| `tests/unit/**` | Pure-function tests (no HTTP, no DB). |
| `tests/integration/**` | ASGI-level tests against the sqlite database and the mocks. |

### `frontend/` and `packages/ui/`

| Path | Single responsibility |
|---|---|
| `frontend/package.json` | Frontend dependencies and scripts. |
| `frontend/next.config.ts` | Standalone output, typed routes, CSP and security headers. |
| `frontend/tsconfig.json` | TS config with the `@/*` path alias. |
| `frontend/postcss.config.mjs` | Tailwind v4 PostCSS plugin. |
| `frontend/vitest.config.ts` | jsdom test environment. |
| `frontend/vitest.setup.ts` | jest-dom matchers. |
| `frontend/playwright.config.ts` | e2e runner configuration. |
| `frontend/Dockerfile` / `Dockerfile.dev` | Production / dev images. |
| `frontend/src/app/layout.tsx` | Fonts, theme provider, auth provider. |
| `frontend/src/app/globals.css` | Imports Tailwind + brand tokens; defines shared utility classes. |
| `frontend/src/app/page.tsx` | Root redirect to `/dashboard`. |
| `frontend/src/app/(public)/layout.tsx` | Centered shell for unauthenticated pages. |
| `frontend/src/app/(public)/login/page.tsx` | Sign-in page. |
| `frontend/src/app/(public)/signup/page.tsx` | Sign-up page. |
| `frontend/src/app/(public)/verify-email/page.tsx` | Consumes the emailed verification token. |
| `frontend/src/app/(public)/oauth-callback/page.tsx` | Finishes a Google sign-in. |
| `frontend/src/app/(authed)/layout.tsx` | Auth gate + global providers. |
| `frontend/src/app/(authed)/dashboard/page.tsx` | Subscription, account token, installs, ingress URLs, deliveries. |
| `frontend/src/app/(authed)/billing/page.tsx` | Subscribe / manage subscription. |
| `frontend/src/app/(authed)/settings/security/page.tsx` | Passkey management. |
| `frontend/src/components/AuthForm.tsx` | Password / Google / passkey sign-in form. |
| `frontend/src/components/AccountShell.tsx` | Top strip + centered content chrome. |
| `frontend/src/components/PasskeyList.tsx` | List, register, rename, delete passkeys. |
| `frontend/src/components/SubscriptionCard.tsx` | Renders subscription state and its call to action. |
| `frontend/src/components/AccountTokenCard.tsx` | Issues/rotates the account token and shows it once. |
| `frontend/src/components/InstallsCard.tsx` | Lists and creates installs. |
| `frontend/src/components/IngressUrlsCard.tsx` | Lists ingress URLs from the backend proxy. |
| `frontend/src/components/DeliveryHistoryCard.tsx` | Lists recent deliveries from the backend proxy. |
| `frontend/src/lib/api.ts` | Fetch wrapper: credentials, CSRF header, 401 refresh-once. |
| `frontend/src/lib/csrf.ts` | Reads the `csrf_token` cookie. |
| `frontend/src/lib/auth-context.tsx` | `useAuth` provider around `/api/v1/auth/me`. |
| `frontend/src/lib/theme.tsx` | next-themes wrapper. |
| `frontend/src/lib/passkey.ts` | Browser WebAuthn ceremonies. |
| `frontend/src/lib/api/billing.ts` | Typed billing endpoint calls. |
| `frontend/src/lib/api/tenants.ts` | Typed tenant endpoint calls. |
| `frontend/src/lib/api/installs.ts` | Typed install endpoint calls. |
| `frontend/e2e/happy-path.spec.ts` | signup → subscribe (stubbed Stripe) → token issued → visible in dashboard. |
| `packages/ui/src/tokens.css` | Brand CSS custom properties (copied verbatim). |
| `packages/ui/src/tailwind.preset.ts` | Font-family preset (copied verbatim). |
| `packages/ui/src/GradientButton.tsx` etc. | Brand primitives (copied verbatim). |
| `packages/ui/src/components/ui/*` | This repo's own shadcn component set. |

### `infra/`

| Path | Single responsibility |
|---|---|
| `infra/main.tf` | Terraform + provider requirements, GCS backend. |
| `infra/variables.tf` | Required, default-free variables for anything environment-identifying. |
| `infra/01_artifact_registry.tf` | Docker repository. |
| `infra/02_database.tf` | Cloud SQL Postgres instance, database, user. |
| `infra/03_secrets.tf` | Secret Manager containers (never values). |
| `infra/04_run_services.tf` | Cloud Run ×2 (frontend, backend) and their service accounts. |
| `infra/05_run_migrate_job.tf` | Cloud Run job that runs `alembic upgrade head`. |
| `infra/06_iam.tf` | Secret accessor and Cloud SQL client bindings. |
| `infra/outputs.tf` | Service URLs and the SQL connection name. |
| `infra/README.md` | States plainly that this is authored, not applied. |

---

### Task 1: Repository scaffold

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/package.json`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/pnpm-workspace.yaml`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/.gitignore`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/.nvmrc`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/Makefile`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-layout.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: pnpm workspace named `saiife-hub` with members `frontend` and `packages/*`; make targets `dev`, `migrate`, `test`, `lint`, `fmt`, `clean`.

- [ ] **Step 1: Write the failing test**

Create `/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-layout.sh`:

```bash
#!/usr/bin/env bash
# Asserts the repository scaffold exists. Run from anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
for f in package.json pnpm-workspace.yaml .gitignore .nvmrc Makefile; do
  if [ ! -f "$ROOT/$f" ]; then
    echo "MISSING: $f"
    fail=1
  fi
done
grep -q '"name": "saiife-hub"' "$ROOT/package.json" || { echo "MISSING: package name saiife-hub"; fail=1; }
grep -q 'packages/\*' "$ROOT/pnpm-workspace.yaml" || { echo "MISSING: packages/* workspace"; fail=1; }
if [ "$fail" -ne 0 ]; then
  echo "LAYOUT CHECK FAILED"
  exit 1
fi
echo "LAYOUT CHECK PASSED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-layout.sh`
Expected: FAIL with "MISSING: package.json" and "LAYOUT CHECK FAILED"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/package.json`:

```json
{
  "name": "saiife-hub",
  "version": "0.1.0",
  "private": true,
  "packageManager": "pnpm@9.12.3",
  "scripts": {
    "dev": "pnpm --filter frontend dev",
    "build": "pnpm -r build",
    "lint": "pnpm -r lint",
    "test": "pnpm -r test",
    "e2e": "pnpm --filter frontend e2e"
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/pnpm-workspace.yaml`:

```yaml
packages:
  - "frontend"
  - "packages/*"
```

`/home/jonasrobinson/projects/saiife/saiife-hub/.nvmrc`:

```
22
```

`/home/jonasrobinson/projects/saiife/saiife-hub/.gitignore`:

```
node_modules/
.next/
.turbo/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db
*.db-journal
.env
.env.local
test-results/
playwright-report/
infra/.terraform/
infra/*.tfstate
infra/*.tfstate.backup
```

`/home/jonasrobinson/projects/saiife/saiife-hub/Makefile`:

```make
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-layout.sh`
Expected: PASS — prints "LAYOUT CHECK PASSED"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add package.json pnpm-workspace.yaml .gitignore .nvmrc Makefile scripts/check-layout.sh
git commit -m "chore: scaffold saiife-hub pnpm workspace root"
```

---

### Task 2: Backend scaffold, settings, logging, health endpoint

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/pyproject.toml`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/config.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/logging.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/rate_limit.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/health/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/health/router.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/__init__.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_health.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.core.config.settings` (a `Settings` instance), `app.core.logging.configure_logging()`, `app.core.rate_limit.limiter`, `app.main.app` (the FastAPI instance), and the error envelope `{"error": {"code": str, "message": str}}`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "test"}


@pytest.mark.asyncio
async def test_unknown_route_returns_error_envelope() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`:

```python
"""Global test setup.

Environment is set BEFORE `app` is imported so `Settings` reads test values.
No network, no GCP, no Postgres: the database is a local sqlite file.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_ROOT / "src"))

os.environ.setdefault("ENV", "test")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_ROOT / 'test-hub.db'}")
os.environ.setdefault("APP_JWT_SECRET", "test-only-jwt-secret-not-a-real-key")
os.environ.setdefault("ACCOUNT_TOKEN_PEPPER", "test-pepper")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
os.environ.setdefault("STRIPE_PRICE_ID", "price_test_not_a_real_price")
os.environ.setdefault("COOKIE_DOMAIN", ".saiife.localhost")
os.environ.setdefault("COOKIE_SECURE", "true")
```

Also create the empty package markers:

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/__init__.py
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_health.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/pyproject.toml`:

```toml
[project]
name = "saiife-hub-backend"
version = "0.1.0"
description = "saiife-hub control plane — identity, billing, tenant lifecycle"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi[standard]>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "aiosqlite>=0.20",
    "alembic>=1.14",
    "httpx[http2]>=0.28",
    "slowapi>=0.1.9",
    "structlog>=24.4",
    "argon2-cffi>=23.1",
    "authlib>=1.3",
    "itsdangerous>=2.2",
    "webauthn>=2.5",
    "pyjwt[crypto]>=2.10",
    "email-validator>=2.2",
    "stripe>=11.1",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "ruff>=0.7.4",
    "mypy>=1.13",
    "respx>=0.21",
]

[tool.uv]
package = false

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "TID", "RUF"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
explicit_package_bases = true
mypy_path = "src"
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["slowapi.*", "authlib.*", "stripe.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
testpaths = ["tests"]
addopts = "--strict-markers --tb=short"
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/config.py`:

```python
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every environment variable the backend reads, in one place.

    Defaults are DEV/TEST values only. This repo is public: no real project ids,
    endpoints, peppers or Stripe keys ever appear here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./hub-dev.db"
    ENV: Literal["dev", "test", "prod"] = "dev"
    LOG_LEVEL: Literal["debug", "info", "warning", "error"] = "info"
    APP_VERSION: str = "dev"

    APP_URL: str = "https://app.saiife.localhost:3001"
    MARKETING_URL: str = "https://saiife.localhost:3000"

    APP_JWT_SECRET: str = "dev-only-change-me"
    APP_JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 15 * 60
    REFRESH_TOKEN_TTL_SECONDS: int = 30 * 24 * 3600

    COOKIE_DOMAIN: str = ".saiife.localhost"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"

    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    MAILGUN_FROM: str = "saiife <noreply@saiife.localhost>"
    MAILGUN_BASE_URL: str = "https://api.eu.mailgun.net"

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = (
        "https://api.saiife.localhost:8000/api/v1/auth/google/callback"
    )

    PASSKEY_RP_ID: str = "saiife.localhost"
    PASSKEY_RP_NAME: str = "saiife"
    PASSKEY_ORIGIN: str = "https://app.saiife.localhost:3001"

    # Account tokens. The pepper is a SECRET and must be identical to the pepper
    # saiife-cloud verifies with — see docs/2026-07-21-saiife-cloud-admin-api-contract.md.
    ACCOUNT_TOKEN_PEPPER: str = "dev-only-pepper-not-a-real-value"

    # saiife-cloud admin API. Empty URL => the in-memory mock is used.
    CLOUD_ADMIN_API_URL: str = ""
    CLOUD_ADMIN_API_KEY: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""
    STRIPE_SIGNATURE_TOLERANCE_SECONDS: int = 300


settings = Settings()
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/logging.py`:

```python
import logging
import sys

import structlog

from .config import settings


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper())
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/core/rate_limit.py`:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/health/router.py`:

```python
from typing import Any

from fastapi import APIRouter

from ....core.config import settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": settings.APP_VERSION}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import settings
from .core.logging import configure_logging
from .core.rate_limit import limiter


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


_is_prod = settings.ENV == "prod"
app = FastAPI(
    title="saiife-hub backend",
    version=settings.APP_VERSION,
    docs_url=None if _is_prod else "/api/v1/docs",
    redoc_url=None if _is_prod else "/api/v1/redoc",
    openapi_url=None if _is_prod else "/api/v1/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, settings.MARKETING_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*", "X-CSRF-Token"],
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "message": "Too many requests — slow down."}},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exc(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(detail)}},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for e in exc.errors():
        ctx = e.get("ctx")
        if ctx:
            e = {**e, "ctx": {k: str(v) if isinstance(v, Exception) else v for k, v in ctx.items()}}
        e.pop("url", None)
        details.append(e)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request body",
                "details": details,
            }
        },
    )


from app.api.v1.health.router import router as health_router  # noqa: E402

app.include_router(health_router)
```

Create the package markers:

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub/backend
mkdir -p src/app/core src/app/api/v1/health
touch src/app/__init__.py src/app/core/__init__.py src/app/api/__init__.py \
      src/app/api/v1/__init__.py src/app/api/v1/health/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_health.py -q`
Expected: PASS — "2 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/pyproject.toml backend/uv.lock backend/src backend/tests
git commit -m "feat: scaffold FastAPI backend with settings, logging, health endpoint"
```

---

### Task 3: Database layer and auth models

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/db/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/db/base.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/db/session.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/user.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_models_roundtrip.py`

**Interfaces:**
- Consumes: `app.core.config.settings.DATABASE_URL`.
- Produces: `app.db.base.Base`, `app.db.session.engine`, `app.db.session.SessionLocal`, `app.db.session.get_db`, and the ORM classes `User`, `Session`, `OAuthAccount`, `EmailVerification`, `Passkey`, `PasskeyChallenge`, `AuthEvent`. All columns use portable SQLAlchemy types (`Uuid`, `String`, `JSON`) so the whole suite runs on sqlite with zero network.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_models_roundtrip.py`:

```python
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import AuthEvent, User


@pytest.mark.asyncio
async def test_user_roundtrips_and_auth_event_links(db_ready: None) -> None:
    uid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(User(id=uid, email="alice@example.com", email_verified_at=datetime.now(UTC)))
        await db.flush()
        db.add(AuthEvent(user_id=uid, event_type="signup", metadata_={"via": "password"}))
        await db.commit()

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == uid))
        assert user is not None
        assert user.email == "alice@example.com"
        event = await db.scalar(select(AuthEvent).where(AuthEvent.user_id == uid))
        assert event is not None
        assert event.event_type == "signup"
        assert event.metadata_ == {"via": "password"}
```

Append to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`:

```python
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def db_ready() -> object:
    """Create a pristine schema before every test, fully offline (sqlite).

    Dropping and recreating rather than truncating keeps each test hermetic and
    avoids maintaining a TRUNCATE list as tables are added.
    """
    from app.db.base import Base
    from app.db.session import engine
    from app import models  # noqa: F401  -- registers every table on Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_models_roundtrip.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.db'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/db/session.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)

if engine.url.drivername.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/user.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    # Stored lowercased by every writer, so a plain unique index is
    # case-insensitive in effect on both Postgres and sqlite.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_jti: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_sub", name="uq_oauth_provider_sub"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Passkey(Base):
    __tablename__ = "passkeys"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(), unique=True, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    transports: Mapped[Optional[list[str]]] = mapped_column(JSON(), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasskeyChallenge(Base):
    __tablename__ = "passkey_challenges"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    challenge: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthEvent(Base):
    __tablename__ = "auth_events"
    id: Mapped[int] = mapped_column(BigInteger(), primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/__init__.py`:

```python
"""Importing this package registers every table on `Base.metadata`."""

from . import user  # noqa: F401

__all__ = ["user"]
```

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub/backend
mkdir -p src/app/db src/app/models
touch src/app/db/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_models_roundtrip.py -q`
Expected: PASS — "1 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/db backend/src/app/models backend/tests
git commit -m "feat: add async SQLAlchemy layer and auth models"
```

---

### Task 4: Alembic setup and the initial auth migration

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic.ini`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/env.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/script.py.mako`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/versions/20260721_1200_initial_auth.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_migrations.py`

**Interfaces:**
- Consumes: `app.db.base.Base`, `app.core.config.settings.DATABASE_URL`.
- Produces: alembic revision `20260721_1200_initial_auth` (`down_revision = None`), applied by `alembic upgrade head`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_migrations.py`:

```python
"""Migrations must build the same schema the ORM expects — offline, on sqlite."""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).parents[2]

EXPECTED_TABLES = {
    "users",
    "sessions",
    "oauth_accounts",
    "email_verifications",
    "passkeys",
    "passkey_challenges",
    "auth_events",
}


@pytest.mark.asyncio
async def test_alembic_upgrade_head_creates_auth_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "migrated.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
        "PYTHONPATH": str(BACKEND / "src"),
    }
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    inspector = inspect(create_engine(f"sqlite:///{db_file}"))
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_migrations.py -q`
Expected: FAIL with "assert 1 == 0" and stderr containing "No config file 'alembic.ini' found"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s
sqlalchemy.url = driver://user:pass@host/db
version_path_separator = os

[post_write_hooks]
hooks = ruff_format
ruff_format.type = console_scripts
ruff_format.entrypoint = ruff
ruff_format.options = format REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARNING
handlers = console
[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/env.py`:

```python
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app import models  # noqa: F401  -- registers every table on Base.metadata
from app.core.config import settings
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/versions/20260721_1200_initial_auth.py`:

```python
"""initial auth schema

Revision ID: 20260721_1200_initial_auth
Revises:
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260721_1200_initial_auth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_jti", sa.String(length=200), nullable=False, unique=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_to", sa.Uuid(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
    )
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_sub", name="uq_oauth_provider_sub"),
    )
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "passkey_challenges",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_events")
    op.drop_table("passkey_challenges")
    op.drop_table("passkeys")
    op.drop_table("email_verifications")
    op.drop_table("oauth_accounts")
    op.drop_table("sessions")
    op.drop_table("users")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_migrations.py -q`
Expected: PASS — "1 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/alembic.ini backend/alembic backend/tests/integration/test_migrations.py
git commit -m "feat: add Alembic setup and initial auth migration"
```

---

### Task 5: Port argon2id password hashing

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/password.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_password.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `hash_password(plaintext: str) -> str`, `verify_password(hashed: str, plaintext: str) -> bool`, `needs_rehash(hashed: str) -> bool`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_password.py`:

```python
from app.auth import password


def test_hash_and_verify_roundtrip() -> None:
    h = password.hash_password("hunter2-correct-horse-battery")
    assert password.verify_password(h, "hunter2-correct-horse-battery") is True


def test_verify_rejects_wrong_password() -> None:
    h = password.hash_password("hunter2-correct-horse-battery")
    assert password.verify_password(h, "wrong-password-attempt") is False


def test_hash_uses_security_enhanced_params() -> None:
    """OWASP security-enhanced floor: m >= 64 MiB, t >= 3, p = 1.

    argon2-cffi encodes params in the hash string, so we read them back.
    """
    h = password.hash_password("anything")
    assert "argon2id" in h
    assert "m=65536" in h
    assert "t=3" in h
    assert "p=1" in h


def test_needs_rehash_returns_false_for_current_params() -> None:
    h = password.hash_password("anything")
    assert password.needs_rehash(h) is False


def test_verify_returns_false_for_garbage_hash() -> None:
    assert password.verify_password("not-a-valid-hash", "any-password") is False
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/__init__.py
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_password.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.auth'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/password.py`:

```python
from __future__ import annotations

import argon2

# OWASP security-enhanced parameters for a product that advertises security.
# memory_cost=64 MiB, time_cost=3, parallelism=1 -> ~50-80ms per hash on 2 vCPU.
_hasher = argon2.PasswordHasher(
    memory_cost=65536,
    time_cost=3,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        _hasher.verify(hashed, plaintext)
    except argon2.exceptions.VerifyMismatchError:
        return False
    except argon2.exceptions.InvalidHashError:
        return False
    except argon2.exceptions.VerificationError:
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """True if the stored hash uses outdated params and should be rehashed
    on the next successful login."""
    return _hasher.check_needs_rehash(hashed)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_password.py -q`
Expected: PASS — "5 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/auth backend/tests/unit
git commit -m "feat: port argon2id password hashing with its test suite"
```

---

### Task 6: Port JWT issuance and verification

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/jwt.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_jwt.py`

**Interfaces:**
- Consumes: `app.core.config.settings.APP_JWT_SECRET`, `.APP_JWT_ALGORITHM`, `.ACCESS_TOKEN_TTL_SECONDS`, `.REFRESH_TOKEN_TTL_SECONDS`.
- Produces: `issue_access(user_id: uuid.UUID, email: str) -> str`, `issue_refresh(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, str]`, `verify_access(token: str) -> AccessClaims`, `verify_refresh(token: str) -> RefreshClaims`, exceptions `InvalidToken` and `InvalidTokenType`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_jwt.py`:

```python
from __future__ import annotations

import uuid

import pytest

from app.auth import jwt as ajwt


def test_issue_and_verify_access_token() -> None:
    uid = uuid.uuid4()
    token = ajwt.issue_access(uid, "alice@example.com")
    claims = ajwt.verify_access(token)
    assert claims.sub == uid
    assert claims.email == "alice@example.com"
    assert claims.type == "access"


def test_issue_and_verify_refresh_token() -> None:
    uid = uuid.uuid4()
    sid = uuid.uuid4()
    token, jti = ajwt.issue_refresh(uid, sid)
    claims = ajwt.verify_refresh(token)
    assert claims.sub == uid
    assert claims.jti == jti
    assert claims.type == "refresh"


def test_verify_access_rejects_refresh_token() -> None:
    refresh, _ = ajwt.issue_refresh(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(ajwt.InvalidTokenType):
        ajwt.verify_access(refresh)


def test_verify_refresh_rejects_access_token() -> None:
    access = ajwt.issue_access(uuid.uuid4(), "alice@example.com")
    with pytest.raises(ajwt.InvalidTokenType):
        ajwt.verify_refresh(access)


def test_verify_rejects_garbage() -> None:
    with pytest.raises(ajwt.InvalidToken):
        ajwt.verify_access("not.a.real.jwt")


def test_verify_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token issued in the past must fail verification once exp has elapsed."""
    real_now = ajwt._now
    monkeypatch.setattr(ajwt, "_now", lambda: real_now() - 3600)
    token = ajwt.issue_access(uuid.uuid4(), "alice@example.com")
    monkeypatch.setattr(ajwt, "_now", real_now)
    with pytest.raises(ajwt.InvalidToken):
        ajwt.verify_access(token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_jwt.py -q`
Expected: FAIL with "ImportError: cannot import name 'jwt' from 'app.auth'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/jwt.py`:

```python
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import jwt as pyjwt

from ..core.config import settings


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class InvalidToken(Exception): ...


class InvalidTokenType(InvalidToken): ...


@dataclass(frozen=True)
class AccessClaims:
    sub: uuid.UUID
    email: str
    type: str
    iat: int
    exp: int
    jti: str


@dataclass(frozen=True)
class RefreshClaims:
    sub: uuid.UUID
    type: str
    iat: int
    exp: int
    jti: str


def issue_access(user_id: uuid.UUID, email: str) -> str:
    now = _now()
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + settings.ACCESS_TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(16),
    }
    return pyjwt.encode(payload, settings.APP_JWT_SECRET, algorithm=settings.APP_JWT_ALGORITHM)


def issue_refresh(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti). Caller writes the jti into sessions.refresh_jti."""
    now = _now()
    jti = f"{session_id}:{secrets.token_urlsafe(16)}"
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + settings.REFRESH_TOKEN_TTL_SECONDS,
        "jti": jti,
    }
    token = pyjwt.encode(
        payload, settings.APP_JWT_SECRET, algorithm=settings.APP_JWT_ALGORITHM
    )
    return token, jti


def _decode(token: str) -> dict[str, Any]:
    try:
        return pyjwt.decode(
            token, settings.APP_JWT_SECRET, algorithms=[settings.APP_JWT_ALGORITHM]
        )
    except pyjwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc


def verify_access(token: str) -> AccessClaims:
    payload = _decode(token)
    if payload.get("type") != "access":
        raise InvalidTokenType(f"expected access, got {payload.get('type')}")
    return AccessClaims(
        sub=uuid.UUID(payload["sub"]),
        email=payload["email"],
        type="access",
        iat=payload["iat"],
        exp=payload["exp"],
        jti=payload["jti"],
    )


def verify_refresh(token: str) -> RefreshClaims:
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise InvalidTokenType(f"expected refresh, got {payload.get('type')}")
    return RefreshClaims(
        sub=uuid.UUID(payload["sub"]),
        type="refresh",
        iat=payload["iat"],
        exp=payload["exp"],
        jti=payload["jti"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_jwt.py -q`
Expected: PASS — "6 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/auth/jwt.py backend/tests/unit/auth/test_jwt.py
git commit -m "feat: port JWT access/refresh issuance and verification"
```

---

### Task 7: Port cookies, CSRF middleware, deps, schemas, audit

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/cookies.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/csrf.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/deps.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/schemas.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/audit.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_csrf.py`

**Interfaces:**
- Consumes: `app.auth.jwt`, `app.db.session.get_db`, `app.models.user.User`, `app.models.user.AuthEvent`.
- Produces: `ACCESS_COOKIE = "s_access"`, `REFRESH_COOKIE = "s_refresh"`, `CSRF_COOKIE = "csrf_token"`, `set_session_cookies(resp, *, access, refresh, csrf)`, `clear_session_cookies(resp)`, `CSRFMiddleware`, `current_user`, `verified_user`, `SignupRequest`, `LoginRequest`, `UserOut`, `VerifyEmailRequest`, `ResendVerificationRequest`, `audit.log_event(db, *, user_id, event_type, request=None, metadata=None)`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_csrf.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_post_without_csrf_header_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post("/api/v1/tenants/account-token", json={}, cookies={"csrf_token": "abc"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_missing"


@pytest.mark.asyncio
async def test_post_with_mismatched_csrf_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post(
            "/api/v1/tenants/account-token",
            json={},
            cookies={"csrf_token": "abc"},
            headers={"X-CSRF-Token": "different"},
        )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_mismatch"


@pytest.mark.asyncio
async def test_get_bypasses_csrf() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_stripe_webhook_is_csrf_exempt() -> None:
    """Stripe cannot carry our CSRF header; the webhook authenticates by signature."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post("/api/v1/billing/webhook", content=b"{}")
    assert r.status_code != 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_csrf.py -q`
Expected: FAIL with "assert 404 == 403" (no CSRF middleware installed, so unknown routes return 404)

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/cookies.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import Response

from ..core.config import settings

ACCESS_COOKIE = "s_access"
REFRESH_COOKIE = "s_refresh"
CSRF_COOKIE = "csrf_token"


def _common() -> dict[str, Any]:
    return {
        "domain": settings.COOKIE_DOMAIN,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }


def set_session_cookies(resp: Response, *, access: str, refresh: str, csrf: str) -> None:
    resp.set_cookie(
        ACCESS_COOKIE, access, httponly=True,
        max_age=settings.ACCESS_TOKEN_TTL_SECONDS, **_common(),
    )
    resp.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS, **_common(),
    )
    # CSRF is readable from JS — the frontend echoes it back as X-CSRF-Token.
    resp.set_cookie(
        CSRF_COOKIE, csrf, httponly=False,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS, **_common(),
    )


def clear_session_cookies(resp: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        resp.delete_cookie(name, domain=settings.COOKIE_DOMAIN, path="/")
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/csrf.py`:

```python
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Routes exempt from the double-submit check: first-trust endpoints that have not
# issued the cookie yet, redirect endpoints Google calls, and the Stripe webhook
# (authenticated by HMAC signature, and Stripe cannot send our header).
_EXEMPT_PREFIXES = (
    "/api/v1/health",
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/resend-verification",
    "/api/v1/auth/google/start",
    "/api/v1/auth/google/callback",
    "/api/v1/auth/passkey/login/start",
    "/api/v1/auth/passkey/login/finish",
    "/api/v1/billing/webhook",
)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in _SAFE_METHODS or _is_exempt(request.url.path):
            return await call_next(request)
        cookie = request.cookies.get("csrf_token")
        header = request.headers.get("x-csrf-token")
        if not cookie or not header:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "csrf_missing", "message": "Missing CSRF token."}},
            )
        if cookie != header:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "csrf_mismatch", "message": "CSRF token mismatch."}},
            )
        return await call_next(request)
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/deps.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db
from ..models.user import User
from . import jwt as ajwt
from .cookies import ACCESS_COOKIE


async def current_user(
    s_access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not s_access:
        raise HTTPException(401, detail={"code": "no_session", "message": "Not authenticated"})
    try:
        claims = ajwt.verify_access(s_access)
    except ajwt.InvalidToken:
        raise HTTPException(
            401, detail={"code": "token_expired", "message": "Session expired"}
        ) from None
    user = await db.scalar(select(User).where(User.id == claims.sub))
    if not user:
        raise HTTPException(
            401, detail={"code": "token_revoked", "message": "Account no longer exists"}
        )
    return user


async def verified_user(user: User = Depends(current_user)) -> User:
    if user.email_verified_at is None:
        raise HTTPException(403, detail={"code": "email_unverified", "message": "Verify your email"})
    return user
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/schemas.py`:

```python
from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    email_verified: bool


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/audit.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import AuthEvent


async def log_event(
    db: AsyncSession,
    *,
    user_id: Optional[uuid.UUID],
    event_type: str,
    request: Optional[Request] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    ip = None
    ua = None
    if request is not None:
        ua = request.headers.get("user-agent")
        if request.client:
            ip = request.client.host
    db.add(
        AuthEvent(
            user_id=user_id,
            event_type=event_type,
            ip=ip,
            user_agent=ua,
            metadata_=dict(metadata) if metadata else None,
        )
    )
    # Caller commits.
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — add the import next to the other `.core` imports and register the middleware immediately after the CORS middleware:

```python
from .auth.csrf import CSRFMiddleware
```

```python
app.add_middleware(CSRFMiddleware)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_csrf.py -q`
Expected: PASS — "4 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/auth backend/src/app/main.py backend/tests/unit/auth/test_csrf.py
git commit -m "feat: port cookies, CSRF middleware, auth deps, schemas and audit log"
```

---

### Task 8: Mailer seam

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/mailer.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/test_mailer.py`

**Interfaces:**
- Consumes: `app.core.config.settings.MAILGUN_*`.
- Produces: `Mailer` protocol with `async send_verification(email: str, link: str) -> None`; `ConsoleMailer`; `MailgunMailer`; `get_mailer() -> Mailer`; `set_mailer(m: Mailer) -> None`; `configure_default_mailer() -> None`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/test_mailer.py`:

```python
import pytest

from app import mailer as mailer_mod


class RecordingMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_verification(self, email: str, link: str) -> None:
        self.sent.append((email, link))


def test_default_mailer_is_console() -> None:
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())
    assert isinstance(mailer_mod.get_mailer(), mailer_mod.ConsoleMailer)


@pytest.mark.asyncio
async def test_set_mailer_replaces_the_active_mailer() -> None:
    rec = RecordingMailer()
    mailer_mod.set_mailer(rec)
    await mailer_mod.get_mailer().send_verification("a@example.com", "https://x/verify?token=t")
    assert rec.sent == [("a@example.com", "https://x/verify?token=t")]
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


def test_configure_default_stays_console_without_mailgun_credentials() -> None:
    """No key + no domain => never attempt a network call."""
    mailer_mod.configure_default_mailer()
    assert isinstance(mailer_mod.get_mailer(), mailer_mod.ConsoleMailer)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/test_mailer.py -q`
Expected: FAIL with "ImportError: cannot import name 'mailer' from 'app'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/mailer.py`:

```python
"""Outbound email behind a seam so tests never touch the network."""
from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from .core.config import settings

log = structlog.get_logger(__name__)


class Mailer(Protocol):
    async def send_verification(self, email: str, link: str) -> None: ...


class ConsoleMailer:
    """Dev/test default: logs the link instead of sending it."""

    async def send_verification(self, email: str, link: str) -> None:
        log.info("verification_email", to=email, link=link)


class MailgunMailer:
    def __init__(self, api_key: str, domain: str, sender: str, base_url: str) -> None:
        self._api_key = api_key
        self._domain = domain
        self._sender = sender
        self._base_url = base_url.rstrip("/")

    async def send_verification(self, email: str, link: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base_url}/v3/{self._domain}/messages",
                auth=("api", self._api_key),
                data={
                    "from": self._sender,
                    "to": email,
                    "subject": "Verify your saiife account",
                    "text": f"Confirm your email address:\n\n{link}\n\nThis link expires in 24 hours.",
                },
            )
            resp.raise_for_status()


_mailer: Mailer = ConsoleMailer()


def get_mailer() -> Mailer:
    return _mailer


def set_mailer(m: Mailer) -> None:
    global _mailer
    _mailer = m


def configure_default_mailer() -> None:
    """Use Mailgun only when BOTH key and domain are configured."""
    if settings.MAILGUN_API_KEY and settings.MAILGUN_DOMAIN:
        set_mailer(
            MailgunMailer(
                settings.MAILGUN_API_KEY,
                settings.MAILGUN_DOMAIN,
                settings.MAILGUN_FROM,
                settings.MAILGUN_BASE_URL,
            )
        )
    else:
        set_mailer(ConsoleMailer())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/test_mailer.py -q`
Expected: PASS — "3 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/mailer.py backend/tests/unit/test_mailer.py
git commit -m "feat: add mailer seam with console and Mailgun implementations"
```

---

### Task 9: Auth router — signup, verify-email, resend, login, logout, me

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_signup_flow.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_login_flow.py`

**Interfaces:**
- Consumes: `app.auth.password`, `app.auth.jwt`, `app.auth.cookies`, `app.auth.deps.current_user`, `app.auth.schemas`, `app.auth.audit`, `app.mailer.get_mailer`, `app.core.rate_limit.limiter`, `app.db.session.get_db`.
- Produces: router at prefix `/api/v1/auth`; helpers `_err(code, message, status)`, `_user_out(user)`, `_hash_token(raw)`, `_start_session(db, user, request, response)`; fixtures `client`, `fake_mailer`, `signed_in_user`.

- [ ] **Step 1: Write the failing test**

Append to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/conftest.py`:

```python
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    from app.core.rate_limit import limiter

    limiter.reset()


@dataclass
class FakeMailer:
    verifications: list[tuple[str, str]] = field(default_factory=list)

    async def send_verification(self, email: str, link: str) -> None:
        self.verifications.append((email, link))


@pytest.fixture
def fake_mailer() -> object:
    from app import mailer as mailer_mod

    fm = FakeMailer()
    mailer_mod.set_mailer(fm)
    yield fm
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


@pytest_asyncio.fixture
async def client() -> object:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def signed_in_user() -> dict[str, object]:
    """A verified user plus the cookies and CSRF token for signed-in requests."""
    from app.auth import jwt as ajwt
    from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        user = User(
            id=_uuid.uuid4(),
            email=f"u-{_uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access = ajwt.issue_access(user.id, user.email)
    refresh, _ = ajwt.issue_refresh(user.id, _uuid.uuid4())
    csrf = "csrf-test-token"
    return {
        "user": user,
        "cookies": {ACCESS_COOKIE: access, REFRESH_COOKIE: refresh, CSRF_COOKIE: csrf},
        "csrf": csrf,
    }
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_signup_flow.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_signup_creates_unverified_user_and_emails_link(client, fake_mailer) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "alice@example.com"
    assert r.json()["email_verified"] is False
    # No session cookies — the user must verify first.
    assert "s_access" not in r.cookies
    assert len(fake_mailer.verifications) == 1
    to, link = fake_mailer.verifications[0]
    assert to == "alice@example.com"
    assert "verify-email?token=" in link


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email(client, fake_mailer) -> None:
    payload = {"email": "alice@example.com", "password": "correct-horse-battery-staple"}
    assert (await client.post("/api/v1/auth/signup", json=payload)).status_code == 201
    r2 = await client.post("/api/v1/auth/signup", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "email_taken"


@pytest.mark.asyncio
async def test_signup_rejects_short_password(client, fake_mailer) -> None:
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "x@example.com", "password": "short"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_resend_verification_is_not_an_enumeration_oracle(client, fake_mailer) -> None:
    known = await client.post(
        "/api/v1/auth/resend-verification", json={"email": "nobody@example.com"}
    )
    assert known.status_code == 200
    assert known.json() == {"ok": True}
    assert fake_mailer.verifications == []
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_login_flow.py`:

```python
import pytest


async def _signup_and_verify(client, fake_mailer, email: str = "alice@example.com"):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    link = fake_mailer.verifications[-1][1]
    token = link.split("token=")[1]
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


@pytest.mark.asyncio
async def test_login_rejects_unverified(client, fake_mailer) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_unverified"


@pytest.mark.asyncio
async def test_login_succeeds_for_verified_user(client, fake_mailer) -> None:
    rv = await _signup_and_verify(client, fake_mailer)
    assert rv.status_code == 200
    assert "s_access" in rv.cookies
    assert "s_refresh" in rv.cookies

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200
    assert "s_access" in r.cookies
    assert "s_refresh" in r.cookies
    assert "csrf_token" in r.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client, fake_mailer) -> None:
    await _signup_and_verify(client, fake_mailer)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "not-the-right-password"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_me_returns_the_signed_in_user(client, signed_in_user) -> None:
    r = await client.get("/api/v1/auth/me", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json()["email"] == signed_in_user["user"].email
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/auth -q`
Expected: FAIL with "assert 404 == 201" (no `/api/v1/auth/signup` route exists)

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`:

```python
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....auth import audit, password
from ....auth import jwt as ajwt
from ....auth.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from ....auth.deps import current_user
from ....auth.schemas import (
    LoginRequest,
    ResendVerificationRequest,
    SignupRequest,
    UserOut,
    VerifyEmailRequest,
)
from ....core.config import settings
from ....core.rate_limit import limiter
from ....db.session import get_db
from ....mailer import get_mailer
from ....models.user import EmailVerification, Session, User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, email_verified=u.email_verified_at is not None)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _start_session(
    db: AsyncSession, user: User, request: Request, response: Response
) -> Session:
    session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_jti="",  # filled below
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(session)
    await db.flush()

    access = ajwt.issue_access(user.id, user.email)
    refresh, jti = ajwt.issue_refresh(user.id, session.id)
    session.refresh_jti = jti
    csrf = secrets.token_urlsafe(32)
    set_session_cookies(response, access=access, refresh=refresh, csrf=csrf)
    return session


@router.post("/signup", status_code=201, response_model=UserOut)
@limiter.limit("5/hour")
async def signup(
    request: Request, body: SignupRequest, db: AsyncSession = Depends(get_db)
) -> UserOut:
    user = User(
        id=uuid.uuid4(),
        email=body.email.lower(),
        password_hash=password.hash_password(body.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _err(
            "email_taken", "An account with this email already exists.", status=409
        ) from None

    raw = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    )
    await audit.log_event(db, user_id=user.id, event_type="signup", request=request)
    await db.commit()

    await get_mailer().send_verification(
        user.email, f"{settings.APP_URL}/verify-email?token={raw}"
    )
    return _user_out(user)


@router.post("/verify-email", response_model=UserOut)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    th = _hash_token(body.token)
    ev = await db.scalar(select(EmailVerification).where(EmailVerification.token_hash == th))
    if ev is None or ev.used_at is not None or ev.expires_at < datetime.now(timezone.utc):
        raise _err(
            "verify_token_invalid", "This verification link is invalid or has expired.", 400
        )
    ev.used_at = datetime.now(timezone.utc)
    user = await db.scalar(select(User).where(User.id == ev.user_id))
    if user is None:
        raise _err("verify_token_invalid", "Account not found.", 400)
    user.email_verified_at = datetime.now(timezone.utc)
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="email_verified", request=request)
    await db.commit()
    return _user_out(user)


@router.post("/resend-verification", status_code=200)
@limiter.limit("1/minute")
async def resend_verification(
    request: Request, body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    # Constant 200 regardless of user existence — no enumeration oracle.
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.email_verified_at is None:
        raw = secrets.token_urlsafe(32)
        db.add(
            EmailVerification(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=_hash_token(raw),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
        )
        await db.commit()
        await get_mailer().send_verification(
            user.email, f"{settings.APP_URL}/verify-email?token={raw}"
        )
    return {"ok": True}


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if (
        user is None
        or user.password_hash is None
        or not password.verify_password(user.password_hash, body.password)
    ):
        raise _err("invalid_credentials", "Email or password is incorrect.", 401)
    if user.email_verified_at is None:
        raise _err("email_unverified", "Verify your email before signing in.", 403)
    if password.needs_rehash(user.password_hash):
        user.password_hash = password.hash_password(body.password)
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_password", request=request)
    await db.commit()
    return _user_out(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> None:
    from sqlalchemy import update

    cookie = request.cookies.get(REFRESH_COOKIE)
    if cookie:
        try:
            claims = ajwt.verify_refresh(cookie)
        except ajwt.InvalidToken:
            pass
        else:
            await db.execute(
                update(Session)
                .where(Session.refresh_jti == claims.jti)
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await audit.log_event(
                db, user_id=claims.sub, event_type="logout", request=request
            )
            await db.commit()
    clear_session_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return _user_out(user)
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — extend the deferred import block at the bottom and register the router, and call `configure_default_mailer()` in `lifespan`:

```python
from .mailer import configure_default_mailer
```

```python
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_default_mailer()
    yield
```

```python
from app.api.v1.auth.router import router as auth_router  # noqa: E402
from app.api.v1.health.router import router as health_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/auth -q`
Expected: PASS — "8 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/api/v1/auth backend/src/app/main.py backend/tests
git commit -m "feat: port auth signup, verify-email, resend, login, logout and me"
```

---

### Task 10: Refresh-token rotation with replay lockdown

**Files:**
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_refresh_rotation.py`

**Interfaces:**
- Consumes: `_start_session`, `_err`, `_user_out`, `app.auth.jwt.verify_refresh`, `app.models.user.Session`.
- Produces: `POST /api/v1/auth/refresh` returning `UserOut` and rotating the refresh cookie; replay revokes every session for the user and emits the `refresh_replay_lockdown` audit event.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_refresh_rotation.py`:

```python
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import AuthEvent


async def _signup_and_verify(client, fake_mailer, email: str = "alice@example.com"):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    link = fake_mailer.verifications[-1][1]
    token = link.split("token=")[1]
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_locks_down_on_replay(client, fake_mailer) -> None:
    rv = await _signup_and_verify(client, fake_mailer)
    old_refresh = rv.cookies["s_refresh"]

    r1 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": old_refresh})
    assert r1.status_code == 200
    new_refresh = r1.cookies["s_refresh"]
    assert new_refresh != old_refresh

    # Replaying the OLD token must fail AND revoke every session.
    r2 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": old_refresh})
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "token_revoked"

    # The rotated NEW token is now dead too — that is the lockdown.
    r3 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": new_refresh})
    assert r3.status_code == 401

    async with SessionLocal() as db:
        events = (
            await db.execute(
                select(AuthEvent.event_type).where(
                    AuthEvent.event_type == "refresh_replay_lockdown"
                )
            )
        ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_refresh_without_cookie_is_401(client) -> None:
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "no_refresh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/auth/test_refresh_rotation.py -q`
Expected: FAIL with "assert 404 == 200" (no `/api/v1/auth/refresh` route exists)

- [ ] **Step 3: Write minimal implementation**

Add to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`, immediately after the `login` handler:

```python
@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> UserOut:
    from sqlalchemy import update

    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise _err("no_refresh", "No refresh token.", 401)
    try:
        claims = ajwt.verify_refresh(cookie)
    except ajwt.InvalidToken:
        raise _err("token_expired", "Refresh token expired.", 401) from None

    session = await db.scalar(select(Session).where(Session.refresh_jti == claims.jti))
    if session is None or session.revoked_at is not None or session.rotated_to is not None:
        # Replay detection — revoke EVERY live session for this user.
        await db.execute(
            update(Session)
            .where(Session.user_id == claims.sub, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await audit.log_event(
            db, user_id=claims.sub, event_type="refresh_replay_lockdown", request=request
        )
        await db.commit()
        clear_session_cookies(response)
        raise _err("token_revoked", "Session revoked.", 401)

    user = await db.scalar(select(User).where(User.id == claims.sub))
    if user is None:
        raise _err("token_revoked", "Account not found.", 401)

    new_session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_jti="",
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(new_session)
    await db.flush()
    new_refresh, new_jti = ajwt.issue_refresh(user.id, new_session.id)
    new_session.refresh_jti = new_jti
    session.rotated_to = new_session.id
    session.revoked_at = datetime.now(timezone.utc)

    access = ajwt.issue_access(user.id, user.email)
    csrf = secrets.token_urlsafe(32)
    set_session_cookies(response, access=access, refresh=new_refresh, csrf=csrf)
    await audit.log_event(db, user_id=user.id, event_type="refresh", request=request)
    await db.commit()
    return _user_out(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/auth/test_refresh_rotation.py -q`
Expected: PASS — "2 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/api/v1/auth/router.py backend/tests/integration/auth/test_refresh_rotation.py
git commit -m "feat: add refresh-token rotation with replay lockdown"
```

---

### Task 11: Google OAuth (PKCE)

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/oauth_google.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_oauth_google.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_oauth_flow.py`

**Interfaces:**
- Consumes: `app.models.user.OAuthAccount`, `app.models.user.User`, `_start_session`.
- Produces: `classify_match(*, google_sub, google_email, google_email_verified, existing_oauth, existing_user_by_email) -> MatchDecision`, `MatchDecision(action, user_id)` with `action` in `{"log_in_existing", "link_and_log_in", "create_new", "reject_unverified_conflict", "reject_google_unverified"}`, `build_client`, `exchange_code`, `fetch_userinfo`, `GOOGLE_AUTH_URL`; routes `GET /api/v1/auth/google/start` and `GET /api/v1/auth/google/callback`; the patchable seam `app.api.v1.auth.router._google_exchange_and_userinfo`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_oauth_google.py`:

```python
import uuid
from datetime import datetime, timezone

from app.auth import oauth_google
from app.models.user import OAuthAccount, User


def _user(email: str, verified: bool = True) -> User:
    u = User(id=uuid.uuid4(), email=email, password_hash=None)
    if verified:
        u.email_verified_at = datetime.now(timezone.utc)
    return u


def test_match_returns_login_for_existing_oauth_account() -> None:
    user = _user("alice@example.com")
    existing = OAuthAccount(
        id=uuid.uuid4(), user_id=user.id, provider="google",
        provider_sub="g-123", email="alice@example.com",
    )
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=existing, existing_user_by_email=user,
    )
    assert decision.action == "log_in_existing"
    assert decision.user_id == user.id


def test_match_links_to_verified_user_with_same_email() -> None:
    user = _user("alice@example.com", verified=True)
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=user,
    )
    assert decision.action == "link_and_log_in"
    assert decision.user_id == user.id


def test_match_refuses_to_link_to_unverified_user() -> None:
    user = _user("alice@example.com", verified=False)
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=user,
    )
    assert decision.action == "reject_unverified_conflict"


def test_match_creates_new_user_when_no_match() -> None:
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="new@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=None,
    )
    assert decision.action == "create_new"


def test_match_rejects_unverified_google_email() -> None:
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="x@example.com", google_email_verified=False,
        existing_oauth=None, existing_user_by_email=None,
    )
    assert decision.action == "reject_google_unverified"
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_oauth_flow.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_google_start_redirects_to_google(client) -> None:
    r = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "code_challenge=" in loc
    assert "code_challenge_method=S256" in loc
    assert "oauth_state" in r.cookies


@pytest.mark.asyncio
async def test_google_callback_creates_user_on_first_login(client) -> None:
    r0 = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    state = r0.headers["location"].split("state=")[1].split("&")[0]

    fake_userinfo = {"sub": "g-12345", "email": "newuser@example.com", "email_verified": True}
    with patch(
        "app.api.v1.auth.router._google_exchange_and_userinfo",
        new=AsyncMock(return_value=fake_userinfo),
    ):
        r = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "fakecode", "state": state},
            follow_redirects=False,
            cookies=r0.cookies,
        )
    assert r.status_code in (302, 303)
    assert "s_access" in r.cookies
    assert "s_refresh" in r.cookies


@pytest.mark.asyncio
async def test_google_callback_rejects_state_mismatch(client) -> None:
    r0 = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    r = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "fakecode", "state": "wrong-state"},
        follow_redirects=False,
        cookies=r0.cookies,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "oauth_state_mismatch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_oauth_google.py tests/integration/auth/test_oauth_flow.py -q`
Expected: FAIL with "ImportError: cannot import name 'oauth_google' from 'app.auth'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/oauth_google.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional, cast

from authlib.integrations.httpx_client import AsyncOAuth2Client

from ..core.config import settings
from ..models.user import OAuthAccount, User

_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

Action = Literal[
    "log_in_existing",
    "link_and_log_in",
    "create_new",
    "reject_unverified_conflict",
    "reject_google_unverified",
]


@dataclass(frozen=True)
class MatchDecision:
    action: Action
    user_id: Optional[uuid.UUID] = None


def classify_match(
    *,
    google_sub: str,
    google_email: str,
    google_email_verified: bool,
    existing_oauth: Optional[OAuthAccount],
    existing_user_by_email: Optional[User],
) -> MatchDecision:
    if not google_email_verified:
        return MatchDecision("reject_google_unverified")
    if existing_oauth is not None:
        return MatchDecision("log_in_existing", user_id=existing_oauth.user_id)
    if existing_user_by_email is not None:
        if existing_user_by_email.email_verified_at is None:
            return MatchDecision("reject_unverified_conflict")
        return MatchDecision("link_and_log_in", user_id=existing_user_by_email.id)
    return MatchDecision("create_new")


def build_client(*, redirect_uri: Optional[str] = None) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scope="openid email profile",
        redirect_uri=redirect_uri or settings.GOOGLE_OAUTH_REDIRECT_URI,
        code_challenge_method="S256",
    )


async def exchange_code(
    client: AsyncOAuth2Client, code: str, code_verifier: str
) -> dict[str, Any]:
    token = await client.fetch_token(_GOOGLE_TOKEN, code=code, code_verifier=code_verifier)
    return cast(dict[str, Any], token)


async def fetch_userinfo(client: AsyncOAuth2Client, access_token: str) -> dict[str, Any]:
    r = await client.get(
        _GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"}
    )
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


GOOGLE_AUTH_URL = _GOOGLE_AUTH
```

Add to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py` — imports at the top:

```python
import base64
from urllib.parse import urlencode

from authlib.common.security import generate_token
from itsdangerous import BadSignature, URLSafeSerializer

from ....auth.oauth_google import (
    GOOGLE_AUTH_URL,
    build_client,
    classify_match,
    exchange_code,
    fetch_userinfo,
)
from ....models.user import OAuthAccount
```

and the handlers at the end of the file:

```python
_state_serializer = URLSafeSerializer(settings.APP_JWT_SECRET, salt="oauth-state")


async def _google_exchange_and_userinfo(code: str, code_verifier: str) -> dict[str, Any]:
    client = build_client()
    token = await exchange_code(client, code, code_verifier)
    return await fetch_userinfo(client, token["access_token"])


@router.get("/google/start")
async def google_start() -> Response:
    code_verifier = generate_token(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    cookie_value = _state_serializer.dumps({"state": state, "verifier": code_verifier})

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    response = Response(
        status_code=302, headers={"location": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}
    )
    response.set_cookie(
        "oauth_state",
        cookie_value,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=600,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request, code: str, state: str, db: AsyncSession = Depends(get_db)
) -> Response:
    raw_state_cookie = request.cookies.get("oauth_state")
    if not raw_state_cookie:
        raise _err("oauth_state_mismatch", "OAuth state missing or expired.", 400)
    try:
        state_data = _state_serializer.loads(raw_state_cookie)
    except BadSignature:
        raise _err("oauth_state_mismatch", "OAuth state signature invalid.", 400) from None
    if state_data.get("state") != state:
        raise _err("oauth_state_mismatch", "OAuth state mismatch.", 400)

    userinfo = await _google_exchange_and_userinfo(code, state_data["verifier"])
    google_sub = userinfo["sub"]
    google_email = str(userinfo["email"]).lower()
    google_email_verified = bool(userinfo.get("email_verified"))

    existing_oauth = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google", OAuthAccount.provider_sub == google_sub
        )
    )
    existing_user = await db.scalar(select(User).where(User.email == google_email))
    decision = classify_match(
        google_sub=google_sub,
        google_email=google_email,
        google_email_verified=google_email_verified,
        existing_oauth=existing_oauth,
        existing_user_by_email=existing_user,
    )

    if decision.action == "reject_google_unverified":
        raise _err("oauth_email_unverified", "Your Google account email is not verified.", 400)
    if decision.action == "reject_unverified_conflict":
        raise _err(
            "oauth_email_unverified_conflict",
            "An unverified account already uses this email — finish email verification first.",
            409,
        )

    if decision.action == "create_new":
        user = User(
            id=uuid.uuid4(),
            email=google_email,
            password_hash=None,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        db.add(
            OAuthAccount(
                id=uuid.uuid4(), user_id=user.id, provider="google",
                provider_sub=google_sub, email=google_email,
            )
        )
        await audit.log_event(
            db, user_id=user.id, event_type="signup", request=request, metadata={"via": "google"}
        )
    elif decision.action == "link_and_log_in":
        assert existing_user is not None  # classify_match guarantees this
        user = existing_user
        db.add(
            OAuthAccount(
                id=uuid.uuid4(), user_id=user.id, provider="google",
                provider_sub=google_sub, email=google_email,
            )
        )
        await audit.log_event(db, user_id=user.id, event_type="google_linked", request=request)
    else:  # log_in_existing
        assert decision.user_id is not None  # classify_match guarantees this
        found = await db.scalar(select(User).where(User.id == decision.user_id))
        assert found is not None  # OAuthAccount.user_id FK guarantees the row exists
        user = found

    response = Response(
        status_code=303, headers={"location": f"{settings.APP_URL}/oauth-callback"}
    )
    response.delete_cookie("oauth_state", domain=settings.COOKIE_DOMAIN, path="/")
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_google", request=request)
    await db.commit()
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_oauth_google.py tests/integration/auth/test_oauth_flow.py -q`
Expected: PASS — "8 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/auth/oauth_google.py backend/src/app/api/v1/auth/router.py backend/tests
git commit -m "feat: port Google OAuth PKCE flow with account-match classification"
```

---

### Task 12: Passkeys (py_webauthn) — ceremonies and management

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/passkeys.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_passkeys.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_passkey_flow.py`

**Interfaces:**
- Consumes: `app.models.user.Passkey`, `app.models.user.PasskeyChallenge`, `current_user`, `_start_session`.
- Produces: `detect_clone(*, stored: int, new: int) -> bool`, `make_registration_options(*, user_id, user_email, excluded_credential_ids) -> tuple[bytes, str]`, `verify_registration(*, challenge, response_json) -> dict`, `make_authentication_options(*, allow_credential_ids) -> tuple[bytes, str]`, `verify_authentication(*, challenge, response_json, public_key, stored_sign_count) -> dict`, `challenge_expiry() -> datetime`; routes `POST /api/v1/auth/passkey/register/start|finish`, `POST /api/v1/auth/passkey/login/start|finish`, `GET /api/v1/auth/passkeys`, `PATCH /api/v1/auth/passkeys/{id}`, `DELETE /api/v1/auth/passkeys/{id}`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/auth/test_passkeys.py`:

```python
from app.auth.passkeys import detect_clone


def test_detect_clone_returns_false_for_increment() -> None:
    assert detect_clone(stored=5, new=6) is False


def test_detect_clone_returns_true_for_decrement() -> None:
    assert detect_clone(stored=5, new=4) is True


def test_detect_clone_returns_true_for_equal_count() -> None:
    """An equal sign_count means the authenticator failed to increment —
    treat as clone evidence per WebAuthn 6.1.1."""
    assert detect_clone(stored=5, new=5) is True


def test_detect_clone_returns_false_when_stored_and_new_are_zero() -> None:
    """A freshly registered passkey has stored=0; some authenticators also
    report 0 on first login. Treat (0, 0) as legitimate first use."""
    assert detect_clone(stored=0, new=0) is False
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/auth/test_passkey_flow.py`:

```python
import uuid

import pytest

from app.db.session import SessionLocal
from app.models.user import Passkey


@pytest.mark.asyncio
async def test_register_start_requires_a_session(client) -> None:
    r = await client.post("/api/v1/auth/passkey/register/start")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_start_returns_challenge_and_options(client, signed_in_user) -> None:
    r = await client.post(
        "/api/v1/auth/passkey/register/start",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert "challenge_id" in body
    assert body["options"]["rp"]["id"] == "saiife.localhost"
    assert "challenge" in body["options"]


@pytest.mark.asyncio
async def test_login_start_is_public_and_allows_discoverable_credentials(client) -> None:
    r = await client.post("/api/v1/auth/passkey/login/start")
    assert r.status_code == 200
    options = r.json()["options"]
    assert "challenge" in options
    # Discoverable-credentials flow: no credential is pinned. py_webauthn may emit
    # an empty list or omit the key entirely; both mean "any registered passkey".
    assert options.get("allowCredentials", []) == []


@pytest.mark.asyncio
async def test_list_rename_and_delete_passkey(client, signed_in_user) -> None:
    user = signed_in_user["user"]
    pk_id = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            Passkey(
                id=pk_id,
                user_id=user.id,
                credential_id=b"cred-1",
                public_key=b"pk-1",
                sign_count=0,
                name="Laptop",
            )
        )
        await db.commit()

    listed = await client.get("/api/v1/auth/passkeys", cookies=signed_in_user["cookies"])
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()] == ["Laptop"]

    renamed = await client.patch(
        f"/api/v1/auth/passkeys/{pk_id}",
        json={"name": "Work laptop"},
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Work laptop"

    deleted = await client.delete(
        f"/api/v1/auth/passkeys/{pk_id}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert deleted.status_code == 204

    listed_again = await client.get("/api/v1/auth/passkeys", cookies=signed_in_user["cookies"])
    assert listed_again.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_passkeys.py tests/integration/auth/test_passkey_flow.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.auth.passkeys'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/auth/passkeys.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    UserVerificationRequirement,
)

from ..core.config import settings


def detect_clone(*, stored: int, new: int) -> bool:
    """True if the authenticator's sign_count looks cloned."""
    if stored == 0 and new == 0:
        return False
    return new <= stored


def make_registration_options(
    *, user_id: uuid.UUID, user_email: str, excluded_credential_ids: list[bytes]
) -> tuple[bytes, str]:
    """Returns (challenge_bytes, options_json)."""
    options = generate_registration_options(
        rp_id=settings.PASSKEY_RP_ID,
        rp_name=settings.PASSKEY_RP_NAME,
        user_id=str(user_id).encode(),
        user_name=user_email,
        user_display_name=user_email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid, type=PublicKeyCredentialType.PUBLIC_KEY)
            for cid in excluded_credential_ids
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    return options.challenge, options_to_json(options)


def verify_registration(*, challenge: bytes, response_json: str) -> dict[str, Any]:
    return verify_registration_response(
        credential=response_json,
        expected_challenge=challenge,
        expected_origin=settings.PASSKEY_ORIGIN,
        expected_rp_id=settings.PASSKEY_RP_ID,
    ).__dict__


def make_authentication_options(*, allow_credential_ids: list[bytes]) -> tuple[bytes, str]:
    options = generate_authentication_options(
        rp_id=settings.PASSKEY_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=cid, type=PublicKeyCredentialType.PUBLIC_KEY)
            for cid in allow_credential_ids
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options.challenge, options_to_json(options)


def verify_authentication(
    *, challenge: bytes, response_json: str, public_key: bytes, stored_sign_count: int
) -> dict[str, Any]:
    return verify_authentication_response(
        credential=response_json,
        expected_challenge=challenge,
        expected_origin=settings.PASSKEY_ORIGIN,
        expected_rp_id=settings.PASSKEY_RP_ID,
        credential_public_key=public_key,
        credential_current_sign_count=stored_sign_count,
    ).__dict__


def challenge_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)
```

Add to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/auth/router.py` — imports:

```python
import json

from ....auth.passkeys import (
    challenge_expiry,
    detect_clone,
    make_authentication_options,
    make_registration_options,
    verify_authentication,
    verify_registration,
)
from ....models.user import Passkey, PasskeyChallenge
```

and the handlers at the end of the file:

```python
@router.post("/passkey/register/start")
async def passkey_register_start(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    existing = (
        await db.execute(select(Passkey.credential_id).where(Passkey.user_id == user.id))
    ).scalars().all()
    challenge_bytes, options_json = make_registration_options(
        user_id=user.id, user_email=user.email, excluded_credential_ids=list(existing)
    )
    ch = PasskeyChallenge(
        id=uuid.uuid4(),
        user_id=user.id,
        challenge=challenge_bytes,
        type="registration",
        expires_at=challenge_expiry(),
    )
    db.add(ch)
    await db.commit()
    return {"challenge_id": str(ch.id), "options": json.loads(options_json)}


@router.post("/passkey/register/finish", status_code=201)
async def passkey_register_finish(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    body = await request.json()
    ch = await db.scalar(
        select(PasskeyChallenge).where(
            PasskeyChallenge.id == uuid.UUID(body["challenge_id"]),
            PasskeyChallenge.user_id == user.id,
            PasskeyChallenge.type == "registration",
        )
    )
    if ch is None or ch.expires_at < datetime.now(timezone.utc):
        raise _err("passkey_challenge_invalid", "Passkey challenge expired — try again.", 400)
    verification = verify_registration(
        challenge=ch.challenge, response_json=json.dumps(body["response"])
    )
    pk = Passkey(
        id=uuid.uuid4(),
        user_id=user.id,
        credential_id=verification["credential_id"],
        public_key=verification["credential_public_key"],
        sign_count=verification["sign_count"],
        transports=body.get("transports"),
        name=body.get("name") or "Unnamed passkey",
    )
    db.add(pk)
    await db.delete(ch)
    await audit.log_event(
        db, user_id=user.id, event_type="passkey_added", request=request,
        metadata={"name": pk.name},
    )
    await db.commit()
    return {"id": str(pk.id), "name": pk.name, "created_at": pk.created_at.isoformat()}


@router.post("/passkey/login/start")
async def passkey_login_start(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    # Discoverable-credentials flow — allow any registered credential.
    challenge_bytes, options_json = make_authentication_options(allow_credential_ids=[])
    ch = PasskeyChallenge(
        id=uuid.uuid4(),
        user_id=None,
        challenge=challenge_bytes,
        type="authentication",
        expires_at=challenge_expiry(),
    )
    db.add(ch)
    await db.commit()
    return {"challenge_id": str(ch.id), "options": json.loads(options_json)}


@router.post("/passkey/login/finish")
async def passkey_login_finish(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    body = await request.json()
    ch = await db.scalar(
        select(PasskeyChallenge).where(
            PasskeyChallenge.id == uuid.UUID(body["challenge_id"]),
            PasskeyChallenge.type == "authentication",
        )
    )
    if ch is None or ch.expires_at < datetime.now(timezone.utc):
        raise _err("passkey_challenge_invalid", "Passkey challenge expired — try again.", 400)
    raw_id = base64.urlsafe_b64decode(body["response"]["rawId"] + "==")
    pk = await db.scalar(select(Passkey).where(Passkey.credential_id == raw_id))
    if pk is None:
        raise _err("passkey_unknown", "This passkey is not registered.", 401)
    verification = verify_authentication(
        challenge=ch.challenge,
        response_json=json.dumps(body["response"]),
        public_key=pk.public_key,
        stored_sign_count=pk.sign_count,
    )
    if detect_clone(stored=pk.sign_count, new=verification["new_sign_count"]):
        await db.delete(pk)
        await audit.log_event(
            db, user_id=pk.user_id, event_type="passkey_clone_detected", request=request,
            metadata={"name": pk.name},
        )
        await db.commit()
        raise _err(
            "passkey_clone_detected",
            "This passkey was cloned and has been revoked. Register a new one.",
            401,
        )
    pk.sign_count = verification["new_sign_count"]
    pk.last_used_at = datetime.now(timezone.utc)
    await db.delete(ch)
    user = await db.scalar(select(User).where(User.id == pk.user_id))
    assert user is not None  # pk.user_id FK guarantees the row exists
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_passkey", request=request)
    await db.commit()
    return _user_out(user).model_dump(mode="json")


@router.get("/passkeys")
async def list_passkeys(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "created_at": p.created_at.isoformat(),
            "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
        }
        for p in rows
    ]


@router.patch("/passkeys/{passkey_id}")
async def rename_passkey(
    passkey_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    body = await request.json()
    pk = await db.scalar(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id)
    )
    if pk is None:
        raise _err("passkey_not_found", "Passkey not found.", 404)
    pk.name = body.get("name") or pk.name
    await db.commit()
    return {"id": str(pk.id), "name": pk.name}


@router.delete("/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(
    passkey_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    pk = await db.scalar(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id)
    )
    if pk is None:
        raise _err("passkey_not_found", "Passkey not found.", 404)
    # Log BEFORE delete so pk.name is still readable.
    await audit.log_event(
        db, user_id=user.id, event_type="passkey_removed", request=request,
        metadata={"name": pk.name},
    )
    await db.delete(pk)
    await db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/auth/test_passkeys.py tests/integration/auth/test_passkey_flow.py -q`
Expected: PASS — "8 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/auth/passkeys.py backend/src/app/api/v1/auth/router.py backend/tests
git commit -m "feat: port passkey ceremonies, clone detection and management routes"
```

---

### Task 13: The CloudControlPlane seam — errors, contracts, protocol

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/errors.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/contracts.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/seam.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_contracts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `NotWiredError(transport: str)`; `CloudError(code: str, message: str)`; dataclasses `CreateTenantRequest(external_ref, tenant_lookup_id, account_token_hash, account_token_hash_algo="scrypt")`, `CloudTenant(tenant_id, tenant_lookup_id, status, created_at)`, `IngressUrl(id, integration, url, created_at)`, `DeliveryRecord(delivery_id, ingress_id, integration, received_at, status)`; protocol `CloudControlPlane` with `create_tenant`, `delete_tenant`, `list_ingress_urls`, `get_delivery_history`; `ADMIN_API_ROUTES` frozen route table.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_contracts.py`:

```python
"""The hub half of the saiife-cloud admin contract, pinned as data.

If these assertions change, docs/2026-07-21-saiife-cloud-admin-api-contract.md
must change with them — the doc is the deliverable saiife-cloud implements.
"""
from dataclasses import asdict

from app.cloud.contracts import (
    ADMIN_API_ROUTES,
    CloudTenant,
    CreateTenantRequest,
    DeliveryRecord,
    IngressUrl,
)
from app.cloud.errors import NotWiredError


def test_create_tenant_request_serialises_to_the_pinned_wire_shape() -> None:
    req = CreateTenantRequest(
        external_ref="hub:sub_123",
        tenant_lookup_id="0123456789abcdef01",
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )
    assert asdict(req) == {
        "external_ref": "hub:sub_123",
        "tenant_lookup_id": "0123456789abcdef01",
        "account_token_hash": "scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "account_token_hash_algo": "scrypt",
    }
    assert req.to_wire() == {
        "externalRef": "hub:sub_123",
        "tenantLookupId": "0123456789abcdef01",
        "accountTokenHash": "scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "accountTokenHashAlgo": "scrypt",
    }


def test_cloud_tenant_parses_the_pinned_camelcase_response() -> None:
    tenant = CloudTenant.from_wire(
        {
            "tenantId": "t_abc",
            "tenantLookupId": "0123456789abcdef01",
            "status": "active",
            "createdAt": "2026-07-21T10:00:00.000Z",
        }
    )
    assert tenant == CloudTenant(
        tenant_id="t_abc",
        tenant_lookup_id="0123456789abcdef01",
        status="active",
        created_at="2026-07-21T10:00:00.000Z",
    )


def test_ingress_url_and_delivery_record_parse_their_pinned_shapes() -> None:
    url = IngressUrl.from_wire(
        {
            "id": "ig_x",
            "integration": "stripe",
            "url": "https://wh.example.invalid/wh/ig_x",
            "createdAt": "2026-07-21T10:00:00.000Z",
        }
    )
    assert url.integration == "stripe"
    assert url.url == "https://wh.example.invalid/wh/ig_x"

    delivery = DeliveryRecord.from_wire(
        {
            "deliveryId": "dl_1",
            "ingressId": "ig_x",
            "integration": "stripe",
            "receivedAt": "2026-07-21T10:00:01.000Z",
            "status": "published",
        }
    )
    assert delivery.delivery_id == "dl_1"
    assert delivery.status == "published"


def test_admin_routes_are_pinned() -> None:
    assert ADMIN_API_ROUTES == {
        "create_tenant": ("POST", "/admin/v1/tenants"),
        "delete_tenant": ("DELETE", "/admin/v1/tenants/{tenant_id}"),
        "list_ingress_urls": ("GET", "/admin/v1/tenants/{tenant_id}/ingress-urls"),
        "get_delivery_history": ("GET", "/admin/v1/tenants/{tenant_id}/deliveries"),
    }


def test_not_wired_error_names_the_transport_and_stays_legible() -> None:
    err = NotWiredError("saiife-cloud admin API transport")
    assert err.transport == "saiife-cloud admin API transport"
    assert "not wired yet" in str(err)
    assert "in-memory mock" in str(err)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_contracts.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.cloud'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/errors.py`:

```python
"""Errors for the saiife-cloud seam.

`NotWiredError` mirrors saiife-cloud's own deferred-transport pattern
(`packages/shared/src/errors.ts`): the transport CONSTRUCTS at startup, but any
real call raises this loud, legible error until the cloud admin API lands.
"""
from __future__ import annotations


class NotWiredError(Exception):
    transport: str

    def __init__(self, transport: str) -> None:
        super().__init__(
            f"{transport} is not wired yet — saiife-cloud does not implement the admin "
            f"API this repo specifies (see docs/2026-07-21-saiife-cloud-admin-api-contract.md). "
            f"This transport is deferred behind its seam; the offline core runs against the "
            f"in-memory mock."
        )
        self.transport = transport


class CloudError(Exception):
    """A structured failure returned by the cloud admin API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/contracts.py`:

```python
"""Wire shapes for the saiife-cloud admin API.

saiife-cloud is TypeScript and uses camelCase on the wire; hub is Python and uses
snake_case internally. Every dataclass here owns exactly one translation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADMIN_API_ROUTES: dict[str, tuple[str, str]] = {
    "create_tenant": ("POST", "/admin/v1/tenants"),
    "delete_tenant": ("DELETE", "/admin/v1/tenants/{tenant_id}"),
    "list_ingress_urls": ("GET", "/admin/v1/tenants/{tenant_id}/ingress-urls"),
    "get_delivery_history": ("GET", "/admin/v1/tenants/{tenant_id}/deliveries"),
}


@dataclass(frozen=True)
class CreateTenantRequest:
    """Create-or-rotate. IDEMPOTENT on `external_ref`.

    If no tenant carries `external_ref`, cloud creates one. If one does, cloud
    REPLACES its lookup id + account token hash (that is token rotation) and
    returns the SAME tenantId. A second call must never yield a second tenant.
    """

    external_ref: str
    tenant_lookup_id: str
    account_token_hash: str
    account_token_hash_algo: str = "scrypt"

    def to_wire(self) -> dict[str, Any]:
        return {
            "externalRef": self.external_ref,
            "tenantLookupId": self.tenant_lookup_id,
            "accountTokenHash": self.account_token_hash,
            "accountTokenHashAlgo": self.account_token_hash_algo,
        }


@dataclass(frozen=True)
class CloudTenant:
    tenant_id: str
    tenant_lookup_id: str
    status: str
    created_at: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> CloudTenant:
        return cls(
            tenant_id=str(raw["tenantId"]),
            tenant_lookup_id=str(raw["tenantLookupId"]),
            status=str(raw["status"]),
            created_at=str(raw["createdAt"]),
        )


@dataclass(frozen=True)
class IngressUrl:
    id: str
    integration: str
    url: str
    created_at: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> IngressUrl:
        return cls(
            id=str(raw["id"]),
            integration=str(raw["integration"]),
            url=str(raw["url"]),
            created_at=str(raw["createdAt"]),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "integration": self.integration,
            "url": self.url,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DeliveryRecord:
    delivery_id: str
    ingress_id: str
    integration: str
    received_at: str
    status: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> DeliveryRecord:
        return cls(
            delivery_id=str(raw["deliveryId"]),
            ingress_id=str(raw["ingressId"]),
            integration=str(raw["integration"]),
            received_at=str(raw["receivedAt"]),
            status=str(raw["status"]),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "ingress_id": self.ingress_id,
            "integration": self.integration,
            "received_at": self.received_at,
            "status": self.status,
        }
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/seam.py`:

```python
"""The single seam between hub and saiife-cloud.

Deliberately NOT named "provision": saiife-cloud already uses
`SubscriptionProvisioner` for Pub/Sub subscription provisioning, which is a
different thing entirely.
"""
from __future__ import annotations

from typing import Protocol

from .contracts import CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl


class CloudControlPlane(Protocol):
    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        """Create-or-rotate a tenant. Idempotent on `request.external_ref`."""
        ...

    async def delete_tenant(self, tenant_id: str) -> None:
        """Remove a tenant and its ingress records. Idempotent: deleting an
        unknown tenant is a no-op, never an error."""
        ...

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        ...

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        ...
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_contracts.py -q`
Expected: PASS — "5 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/cloud backend/tests/unit/cloud
git commit -m "feat: define the CloudControlPlane seam, wire contracts and NotWiredError"
```

---

### Task 14: In-memory CloudControlPlane mock

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/mock.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_mock.py`

**Interfaces:**
- Consumes: `CloudControlPlane`, `CreateTenantRequest`, `CloudTenant`, `IngressUrl`, `DeliveryRecord`.
- Produces: `InMemoryCloudControlPlane` implementing `CloudControlPlane`, plus test affordances `seed_ingress_url(tenant_id, ingress)`, `seed_delivery(tenant_id, delivery)`, `create_calls: list[CreateTenantRequest]`, `delete_calls: list[str]`, `tenants: dict[str, CloudTenant]`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_mock.py`:

```python
import pytest

from app.cloud.contracts import CreateTenantRequest, DeliveryRecord, IngressUrl
from app.cloud.mock import InMemoryCloudControlPlane


def _req(external_ref: str = "hub:sub_1", lookup: str = "0123456789abcdef01") -> CreateTenantRequest:
    return CreateTenantRequest(
        external_ref=external_ref,
        tenant_lookup_id=lookup,
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )


@pytest.mark.asyncio
async def test_create_tenant_returns_an_active_tenant_with_a_t_prefixed_id() -> None:
    cloud = InMemoryCloudControlPlane()
    tenant = await cloud.create_tenant(_req())
    assert tenant.tenant_id.startswith("t_")
    assert tenant.tenant_lookup_id == "0123456789abcdef01"
    assert tenant.status == "active"
    assert cloud.create_calls == [_req()]


@pytest.mark.asyncio
async def test_create_tenant_is_idempotent_on_external_ref() -> None:
    """The contract's core guarantee: a Stripe retry must not double-create."""
    cloud = InMemoryCloudControlPlane()
    first = await cloud.create_tenant(_req())
    second = await cloud.create_tenant(_req())
    assert first.tenant_id == second.tenant_id
    assert len(cloud.tenants) == 1


@pytest.mark.asyncio
async def test_create_tenant_with_same_external_ref_rotates_the_token_hash() -> None:
    cloud = InMemoryCloudControlPlane()
    first = await cloud.create_tenant(_req(lookup="aaaaaaaaaaaaaaaaaa"))
    rotated = await cloud.create_tenant(_req(lookup="bbbbbbbbbbbbbbbbbb"))
    assert rotated.tenant_id == first.tenant_id
    assert rotated.tenant_lookup_id == "bbbbbbbbbbbbbbbbbb"
    assert cloud.tenants[first.tenant_id].tenant_lookup_id == "bbbbbbbbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_delete_tenant_removes_it_and_is_idempotent() -> None:
    cloud = InMemoryCloudControlPlane()
    tenant = await cloud.create_tenant(_req())
    await cloud.delete_tenant(tenant.tenant_id)
    assert cloud.tenants == {}
    await cloud.delete_tenant(tenant.tenant_id)  # no raise
    assert cloud.delete_calls == [tenant.tenant_id, tenant.tenant_id]


@pytest.mark.asyncio
async def test_list_ingress_urls_and_delivery_history_are_scoped_to_the_tenant() -> None:
    cloud = InMemoryCloudControlPlane()
    a = await cloud.create_tenant(_req("hub:sub_a", "aaaaaaaaaaaaaaaaaa"))
    b = await cloud.create_tenant(_req("hub:sub_b", "bbbbbbbbbbbbbbbbbb"))
    cloud.seed_ingress_url(
        a.tenant_id,
        IngressUrl(
            id="ig_a", integration="stripe",
            url="https://wh.example.invalid/wh/ig_a", created_at="2026-07-21T10:00:00.000Z",
        ),
    )
    cloud.seed_delivery(
        a.tenant_id,
        DeliveryRecord(
            delivery_id="dl_a", ingress_id="ig_a", integration="stripe",
            received_at="2026-07-21T10:00:01.000Z", status="published",
        ),
    )
    assert [u.id for u in await cloud.list_ingress_urls(a.tenant_id)] == ["ig_a"]
    assert await cloud.list_ingress_urls(b.tenant_id) == []
    assert [d.delivery_id for d in await cloud.get_delivery_history(a.tenant_id)] == ["dl_a"]
    assert await cloud.get_delivery_history(b.tenant_id) == []


@pytest.mark.asyncio
async def test_delivery_history_honours_the_limit_newest_first() -> None:
    cloud = InMemoryCloudControlPlane()
    t = await cloud.create_tenant(_req())
    for i in range(5):
        cloud.seed_delivery(
            t.tenant_id,
            DeliveryRecord(
                delivery_id=f"dl_{i}", ingress_id="ig_a", integration="stripe",
                received_at=f"2026-07-21T10:00:0{i}.000Z", status="published",
            ),
        )
    got = await cloud.get_delivery_history(t.tenant_id, limit=2)
    assert [d.delivery_id for d in got] == ["dl_4", "dl_3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_mock.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.cloud.mock'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/mock.py`:

```python
"""In-memory CloudControlPlane. EVERY test runs against this — no network.

Mirrors saiife-cloud's own `packages/shared/src/mocks.ts` pattern: deterministic,
inspectable, and recording every call so a test can prove idempotency.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .contracts import CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class InMemoryCloudControlPlane:
    def __init__(self) -> None:
        self.tenants: dict[str, CloudTenant] = {}
        self._by_external_ref: dict[str, str] = {}
        self._ingress: dict[str, list[IngressUrl]] = {}
        self._deliveries: dict[str, list[DeliveryRecord]] = {}
        self.create_calls: list[CreateTenantRequest] = []
        self.delete_calls: list[str] = []

    # --- seam methods ----------------------------------------------------

    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        self.create_calls.append(request)
        existing_id = self._by_external_ref.get(request.external_ref)
        if existing_id is not None:
            # Same externalRef => rotate in place, same tenantId. Never a second tenant.
            previous = self.tenants[existing_id]
            rotated = CloudTenant(
                tenant_id=previous.tenant_id,
                tenant_lookup_id=request.tenant_lookup_id,
                status=previous.status,
                created_at=previous.created_at,
            )
            self.tenants[existing_id] = rotated
            return rotated

        tenant_id = "t_" + secrets.token_urlsafe(12).replace("=", "")
        tenant = CloudTenant(
            tenant_id=tenant_id,
            tenant_lookup_id=request.tenant_lookup_id,
            status="active",
            created_at=_now_iso(),
        )
        self.tenants[tenant_id] = tenant
        self._by_external_ref[request.external_ref] = tenant_id
        self._ingress.setdefault(tenant_id, [])
        self._deliveries.setdefault(tenant_id, [])
        return tenant

    async def delete_tenant(self, tenant_id: str) -> None:
        self.delete_calls.append(tenant_id)
        self.tenants.pop(tenant_id, None)
        self._ingress.pop(tenant_id, None)
        self._deliveries.pop(tenant_id, None)
        for ref, tid in list(self._by_external_ref.items()):
            if tid == tenant_id:
                del self._by_external_ref[ref]

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        return list(self._ingress.get(tenant_id, []))

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        records = self._deliveries.get(tenant_id, [])
        return list(reversed(records))[:limit]

    # --- test affordances ------------------------------------------------

    def seed_ingress_url(self, tenant_id: str, ingress: IngressUrl) -> None:
        self._ingress.setdefault(tenant_id, []).append(ingress)

    def seed_delivery(self, tenant_id: str, delivery: DeliveryRecord) -> None:
        self._deliveries.setdefault(tenant_id, []).append(delivery)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_mock.py -q`
Expected: PASS — "6 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/cloud/mock.py backend/tests/unit/cloud/test_mock.py
git commit -m "feat: add in-memory CloudControlPlane mock with idempotent create-or-rotate"
```

---

### Task 15: Deferred HTTP CloudControlPlane and the selection seam

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/http.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/deps.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_http_deferred.py`

**Interfaces:**
- Consumes: `CloudControlPlane`, `NotWiredError`, `settings.CLOUD_ADMIN_API_URL`, `settings.CLOUD_ADMIN_API_KEY`.
- Produces: `HttpCloudControlPlane(base_url: str, api_key: str)` — constructs successfully, raises `NotWiredError` from every method; `get_cloud() -> CloudControlPlane`; `set_cloud(c: CloudControlPlane) -> None`; `configure_default_cloud() -> None`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_http_deferred.py`:

```python
import pytest

from app.cloud.contracts import CreateTenantRequest
from app.cloud.deps import configure_default_cloud, get_cloud, set_cloud
from app.cloud.errors import NotWiredError
from app.cloud.http import HttpCloudControlPlane
from app.cloud.mock import InMemoryCloudControlPlane


def test_http_transport_constructs_at_startup() -> None:
    """Constructing must succeed so the app boots; only calls are deferred."""
    plane = HttpCloudControlPlane("https://cloud.example.invalid", "admin-key")
    assert plane.base_url == "https://cloud.example.invalid"


def test_http_transport_rejects_an_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        HttpCloudControlPlane("", "admin-key")


@pytest.mark.asyncio
async def test_every_http_method_raises_not_wired() -> None:
    plane = HttpCloudControlPlane("https://cloud.example.invalid", "admin-key")
    req = CreateTenantRequest(
        external_ref="hub:sub_1",
        tenant_lookup_id="0123456789abcdef01",
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )
    with pytest.raises(NotWiredError):
        await plane.create_tenant(req)
    with pytest.raises(NotWiredError):
        await plane.delete_tenant("t_x")
    with pytest.raises(NotWiredError):
        await plane.list_ingress_urls("t_x")
    with pytest.raises(NotWiredError):
        await plane.get_delivery_history("t_x")


def test_default_cloud_is_the_mock_when_no_admin_url_is_configured() -> None:
    configure_default_cloud()
    assert isinstance(get_cloud(), InMemoryCloudControlPlane)


def test_set_cloud_replaces_the_active_control_plane() -> None:
    replacement = InMemoryCloudControlPlane()
    set_cloud(replacement)
    assert get_cloud() is replacement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_http_deferred.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.cloud.deps'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/http.py`:

```python
"""DEFERRED live transport for the saiife-cloud admin API.

saiife-cloud exposes exactly two routes today — `/v1/ingress-urls` and
`/v1/drain-token` — both authenticated AS an existing tenant. There is no route
that creates one, and hub cannot authenticate as a tenant anyway because it stores
only the token HASH. The admin API this class targets is specified in
docs/2026-07-21-saiife-cloud-admin-api-contract.md and does not exist yet.

Constructing this class succeeds so the app boots; every call raises NotWiredError.
When cloud implements the contract, replace each `_not_wired()` with the httpx call
already sketched in the docstring of each method.
"""
from __future__ import annotations

from typing import NoReturn

from .contracts import ADMIN_API_ROUTES, CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl

_TRANSPORT = "saiife-cloud admin API transport"


class HttpCloudControlPlane:
    def __init__(self, base_url: str, api_key: str) -> None:
        if not base_url:
            raise ValueError("HttpCloudControlPlane requires a non-empty base_url.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _not_wired(self) -> NoReturn:
        from .errors import NotWiredError

        raise NotWiredError(_TRANSPORT)

    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        """POST {base_url}/admin/v1/tenants, body `request.to_wire()`,
        `Authorization: Bearer <api_key>`, `Idempotency-Key: <external_ref>`."""
        assert ADMIN_API_ROUTES["create_tenant"] == ("POST", "/admin/v1/tenants")
        self._not_wired()

    async def delete_tenant(self, tenant_id: str) -> None:
        """DELETE {base_url}/admin/v1/tenants/{tenant_id}. 404 is treated as success."""
        self._not_wired()

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        """GET {base_url}/admin/v1/tenants/{tenant_id}/ingress-urls
        -> `{"ingressUrls": IngressUrl[]}`."""
        self._not_wired()

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        """GET {base_url}/admin/v1/tenants/{tenant_id}/deliveries?limit=N
        -> `{"deliveries": DeliveryRecord[]}`."""
        self._not_wired()
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/cloud/deps.py`:

```python
"""Chooses the live or mock control plane and exposes it as a FastAPI dependency."""
from __future__ import annotations

from ..core.config import settings
from .http import HttpCloudControlPlane
from .mock import InMemoryCloudControlPlane
from .seam import CloudControlPlane

_cloud: CloudControlPlane = InMemoryCloudControlPlane()


def get_cloud() -> CloudControlPlane:
    return _cloud


def set_cloud(c: CloudControlPlane) -> None:
    global _cloud
    _cloud = c


def configure_default_cloud() -> None:
    """No admin URL configured => the in-memory mock. This is what makes the
    whole repo buildable and testable with no GCP account and no network."""
    if settings.CLOUD_ADMIN_API_URL:
        set_cloud(
            HttpCloudControlPlane(settings.CLOUD_ADMIN_API_URL, settings.CLOUD_ADMIN_API_KEY)
        )
    else:
        set_cloud(InMemoryCloudControlPlane())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud -q`
Expected: PASS — "16 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/cloud/http.py backend/src/app/cloud/deps.py backend/tests/unit/cloud
git commit -m "feat: add deferred HTTP cloud transport and the control-plane selection seam"
```

---

### Task 16: The saiife-cloud admin-API contract document

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/docs/2026-07-21-saiife-cloud-admin-api-contract.md`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_contract_doc.py`

**Interfaces:**
- Consumes: `app.cloud.contracts.ADMIN_API_ROUTES`, `app.tenants.tokens` constants (referenced by name only — this task does not import them).
- Produces: the deliverable document saiife-cloud implements. The test asserts the doc and the code cannot drift.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/cloud/test_contract_doc.py`:

```python
"""The contract doc is a DELIVERABLE, not prose — keep it pinned to the code."""
from pathlib import Path

from app.cloud.contracts import ADMIN_API_ROUTES

DOC = Path(__file__).parents[3].parent / "docs" / "2026-07-21-saiife-cloud-admin-api-contract.md"


def test_contract_doc_exists() -> None:
    assert DOC.is_file(), f"missing contract deliverable at {DOC}"


def test_contract_doc_documents_every_route() -> None:
    text = DOC.read_text()
    for method, path in ADMIN_API_ROUTES.values():
        literal = path.replace("{tenant_id}", "{tenantId}")
        assert f"{method} {literal}" in text, f"undocumented route: {method} {literal}"


def test_contract_doc_pins_the_hash_scheme_and_shared_pepper() -> None:
    text = DOC.read_text()
    assert "scrypt$16384$8$1$" in text
    assert "N=16384" in text
    assert "shared pepper" in text.lower()
    assert "sfc_<tenantLookupId>_<secret>" in text


def test_contract_doc_states_idempotency_on_external_ref() -> None:
    text = DOC.read_text()
    assert "externalRef" in text
    assert "idempotent" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_contract_doc.py -q`
Expected: FAIL with "AssertionError: missing contract deliverable at .../docs/2026-07-21-saiife-cloud-admin-api-contract.md"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/docs/2026-07-21-saiife-cloud-admin-api-contract.md`:

````markdown
# saiife-cloud admin API — the contract saiife-hub needs

**Status:** Proposed by saiife-hub. Not implemented in saiife-cloud.
**Date:** 2026-07-21
**Audience:** whoever wires saiife-cloud.

## Why this document exists

saiife-cloud's control-api exposes exactly two routes — `GET/POST /v1/ingress-urls`
and `POST /v1/drain-token` — and both authenticate **as an existing tenant** via
`Authorization: Bearer sfc_<tenantLookupId>_<secret>`. There is no route that
creates a tenant. Cloud reads tenants from a `TenantStore` that nothing writes to.

saiife-hub is the thing that must write that record. It cannot use the existing
tenant-authenticated routes for anything, because **hub never holds an account
token in plaintext** — it stores only the scrypt hash, exactly as cloud does. So
hub needs a separate, service-authenticated admin surface.

This document specifies that surface. saiife-hub already codes against it:
`backend/src/app/cloud/http.py` is written to these routes and raises
`NotWiredError` until they exist.

## Vocabulary

"Create a tenant" is **not** "provision a subscription". saiife-cloud already uses
`SubscriptionProvisioner` / `GcpSubscriptionProvisioner` to mean Pub/Sub
subscription provisioning. This document says `createTenant` / `deleteTenant` and
never says "provision" for tenant lifecycle.

## Authentication

`Authorization: Bearer <adminApiKey>` — a service credential held by hub's Cloud
Run service account and stored in Secret Manager on both sides. It is **not** an
account token and must not be accepted by `/v1/*`. Conversely an account token
must not be accepted by `/admin/v1/*`.

Recommended hardening: restrict `/admin/v1/*` to hub's service account identity at
the ingress layer in addition to the bearer key.

## The shared pepper — the one hard operational coupling

Account tokens are `sfc_<tenantLookupId>_<secret>` (cloud's
`packages/shared/src/ids.ts`). Hub mints the token, hashes the secret half, shows
the plaintext to the user exactly once, and stores only the hash. Cloud verifies
the presented token against that stored hash.

For that to work, **hub and cloud must use the same pepper value**. The pepper is
mixed into the password side of the hash:

```
scrypt(password = f"{pepper}:{secret}", salt = <16 random bytes>,
       N = 16384, r = 8, p = 1, dklen = 32)
```

Stored, self-describing, exactly as cloud's `hashAccountSecret` already emits:

```
scrypt$16384$8$1$<saltBase64>$<hashBase64>
```

Verified golden vector (`pepper = "test-pepper"`, `secret = "s3cret"`, salt = 16
bytes of `0x07`) — Python's `hashlib.scrypt` and Node's `crypto.scryptSync`
produce byte-identical output:

```
scrypt$16384$8$1$BwcHBwcHBwcHBwcHBwcHBw==$mxQuZODDRxgYwpXcqbCDE3nCvTiE47xP78i9l3YCC5k=
```

**Operationally:** one Secret Manager secret, `account-token-pepper`, replicated to
both projects, rotated together. Rotating the pepper invalidates every issued
token; treat it as a break-glass action, not routine maintenance.

## Routes

All request and response bodies are JSON, camelCase, matching cloud's existing
`packages/shared/src/contracts.ts` style. Errors use cloud's existing envelope:
`{"error": {"code": "...", "message": "..."}}`.

### `POST /admin/v1/tenants` — create or rotate

**Idempotent on `externalRef`.** This is the load-bearing property: Stripe retries
webhooks, and double-creating a tenant is a real failure mode.

- If no tenant carries `externalRef`, create one: generate `tenantId` (`t_` +
  base64url of 16 random bytes, per `newTenantId()`), store `tenantLookupId`,
  `accountTokenHash`, `accountTokenHashAlgo`, `status: "active"`, `subscription: null`.
- If a tenant already carries `externalRef`, **replace** its `tenantLookupId` and
  `accountTokenHash` and return the **same** `tenantId`. That single behaviour is
  both retry-safety and account-token rotation.
- Never create a second tenant for the same `externalRef`.

Request:

```json
{
  "externalRef": "hub:sub_1Nx0000000000000",
  "tenantLookupId": "0123456789abcdef01",
  "accountTokenHash": "scrypt$16384$8$1$BwcHBwcHBwcHBwcHBwcHBw==$mxQuZODDRxgYwpXcqbCDE3nCvTiE47xP78i9l3YCC5k=",
  "accountTokenHashAlgo": "scrypt"
}
```

Response `200`:

```json
{
  "tenantId": "t_9f3aQxK1m2n3o4p5",
  "tenantLookupId": "0123456789abcdef01",
  "status": "active",
  "createdAt": "2026-07-21T10:00:00.000Z"
}
```

`externalRef` is opaque to cloud. Hub uses `hub:<stripe_subscription_id>`. Cloud
must store it and index it uniquely.

`tenantLookupId` must be unique across tenants; a collision is `409
tenant_lookup_id_taken`. Hub generates 9 random bytes (18 hex chars), so a
collision means "retry", not "fail".

### `DELETE /admin/v1/tenants/{tenantId}` — delete

Removes the tenant and its `ingressUrls/*` records. **Idempotent:** deleting an
unknown tenant returns `204`, never `404`. Hub calls this on
`customer.subscription.deleted`, and Stripe retries that too.

Response: `204` with no body.

Cloud may prefer a soft delete (`status: "suspended"`) for a grace window;
`resolveIngress` already returns null for a suspended tenant, so ingest stops
either way. If cloud chooses soft delete, this route must still be idempotent and
must still make the tenant's ingress unresolvable.

### `GET /admin/v1/tenants/{tenantId}/ingress-urls` — list

The same data as the tenant-authenticated `GET /v1/ingress-urls`, reachable with
the admin credential so hub can render it in the dashboard without holding an
account token.

Response `200`:

```json
{
  "ingressUrls": [
    {
      "id": "ig_Ab12Cd34Ef56Gh78",
      "integration": "stripe",
      "url": "https://wh.example.invalid/wh/ig_Ab12Cd34Ef56Gh78",
      "createdAt": "2026-07-21T10:00:00.000Z"
    }
  ]
}
```

Shape is byte-identical to `ListIngressUrlsResponse` in
`packages/shared/src/contracts.ts`. Do not fork it.

### `GET /admin/v1/tenants/{tenantId}/deliveries` — recent delivery history

Query: `?limit=<1..200>`, default `50`. Newest first.

**This requires something cloud does not have today.** Cloud's Firestore model
(`tenants/*`, `ingressUrls/*`, `rateCounters/*`) persists no delivery log; the
relay publishes to Pub/Sub and forgets. Implementing this route means adding a
bounded, short-retention delivery index — e.g. `deliveries/{deliveryId}` holding
only `{tenantId, ingressId, integration, receivedAt, status}` with a TTL matching
Pub/Sub's 7-day buffer.

**It must not store body bytes or headers.** The relay's privacy framing is that
payloads transit and are buffered, not that they are indexed and retained by an
account-facing service. Metadata only.

Response `200`:

```json
{
  "deliveries": [
    {
      "deliveryId": "dl_01J8Z0X0000000000000000000",
      "ingressId": "ig_Ab12Cd34Ef56Gh78",
      "integration": "stripe",
      "receivedAt": "2026-07-21T10:00:01.000Z",
      "status": "published"
    }
  ]
}
```

`status` is one of `published`, `rate_limited`, `rejected`.

If cloud prefers not to build this, hub degrades gracefully: the dashboard's
delivery panel renders an empty state. It is the least important of the four.

## What hub does NOT ask for

- No route that returns an account token, hash, or pepper.
- No route that reads webhook bodies or headers.
- No broad GCP credential. Hub never pulls Pub/Sub; only the desktop client does,
  via the existing `POST /v1/drain-token`.

## Alternatives considered

- **Hub writes Firestore directly.** Fewer moving parts, but it makes hub's service
  account a writer on cloud's private data model and couples two repos to one
  schema with no version boundary. Rejected.
- **Extend `/v1/*` with a tenant-creating route.** Impossible: those routes
  authenticate as a tenant, and creation is precisely the case where no tenant
  exists.
- **Hub sends the plaintext secret and lets cloud hash it.** Removes the shared
  pepper, but puts a plaintext long-lived credential on a service-to-service wire
  and in cloud's request logs. Rejected.

The decision about which mechanism cloud actually adopts belongs with saiife-cloud.
This document is hub's proposal and the shape hub is already coded against.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/cloud/test_contract_doc.py -q`
Expected: PASS — "4 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add docs/2026-07-21-saiife-cloud-admin-api-contract.md backend/tests/unit/cloud/test_contract_doc.py
git commit -m "docs: specify the saiife-cloud admin API contract hub requires"
```

---

### Task 17: Account token minting and parsing (`sfc_`)

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/tokens.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants/test_token_format.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ACCOUNT_TOKEN_PREFIX = "sfc_"`, `new_tenant_lookup_id() -> str`, `GeneratedAccountToken(token, tenant_lookup_id, secret)`, `generate_account_token(tenant_lookup_id: str | None = None) -> GeneratedAccountToken`, `ParsedAccountToken(tenant_lookup_id, secret)`, `parse_account_token(token: object) -> ParsedAccountToken | None`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants/test_token_format.py`:

```python
"""The token format is pinned by saiife-cloud/packages/shared/src/ids.ts.

Every assertion here mirrors a behaviour of `generateAccountToken` /
`parseAccountToken` in that file. If one fails, hub and cloud have diverged and
cloud will reject hub-issued tokens.
"""
import base64
import re

from app.tenants.tokens import (
    ACCOUNT_TOKEN_PREFIX,
    generate_account_token,
    new_tenant_lookup_id,
    parse_account_token,
)


def test_prefix_is_sfc_underscore() -> None:
    assert ACCOUNT_TOKEN_PREFIX == "sfc_"


def test_lookup_id_is_18_lowercase_hex_chars_and_never_contains_underscore() -> None:
    """Cloud splits on the FIRST '_'; hex guarantees that split is unambiguous."""
    for _ in range(20):
        lookup = new_tenant_lookup_id()
        assert re.fullmatch(r"[0-9a-f]{18}", lookup), lookup


def test_generated_token_is_prefix_lookup_underscore_secret() -> None:
    gen = generate_account_token()
    assert gen.token == f"sfc_{gen.tenant_lookup_id}_{gen.secret}"


def test_secret_is_32_random_bytes_base64url_without_padding() -> None:
    gen = generate_account_token()
    assert "=" not in gen.secret
    assert re.fullmatch(r"[A-Za-z0-9_-]+", gen.secret)
    decoded = base64.urlsafe_b64decode(gen.secret + "=" * (-len(gen.secret) % 4))
    assert len(decoded) == 32


def test_generate_accepts_an_explicit_lookup_id() -> None:
    gen = generate_account_token("0123456789abcdef01")
    assert gen.tenant_lookup_id == "0123456789abcdef01"
    assert gen.token.startswith("sfc_0123456789abcdef01_")


def test_tokens_are_unique_across_calls() -> None:
    tokens = {generate_account_token().token for _ in range(50)}
    assert len(tokens) == 50


def test_parse_roundtrips_a_generated_token() -> None:
    gen = generate_account_token()
    parsed = parse_account_token(gen.token)
    assert parsed is not None
    assert parsed.tenant_lookup_id == gen.tenant_lookup_id
    assert parsed.secret == gen.secret


def test_parse_splits_on_the_first_underscore_so_base64url_secrets_survive() -> None:
    parsed = parse_account_token("sfc_0123456789abcdef01_aa_bb-cc")
    assert parsed is not None
    assert parsed.tenant_lookup_id == "0123456789abcdef01"
    assert parsed.secret == "aa_bb-cc"


def test_parse_returns_none_for_every_malformed_token() -> None:
    for bad in [
        None,
        42,
        "",
        "nope",
        "sfc_",
        "sfc_onlylookup",
        "sfc__secret",          # empty lookup id
        "sfc_lookup_",          # empty secret
        "sfc_look up_secret",   # space in lookup id
        "sfc_lookup_sec ret",   # space in secret
        "SFC_lookup_secret",    # wrong-case prefix
    ]:
        assert parse_account_token(bad) is None, bad
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/tenants/test_token_format.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.tenants'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/tokens.py`:

```python
"""Account tokens — `sfc_<tenantLookupId>_<secret>`.

PINNED BY saiife-cloud. The reference implementations are
`packages/shared/src/ids.ts` (format) and `packages/control-api/src/auth.ts`
(hashing). Any change here is a breaking change for every desktop install.

- `tenantLookupId` is NON-SECRET: it lets cloud find the tenant without a scan.
  It is HEX so it can never contain the `_` that separates it from the secret.
- `secret` is 32 random bytes (256 bits) base64url, unpadded.
- The plaintext token is shown to the user ONCE and never stored, logged, or echoed.
"""
from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass

ACCOUNT_TOKEN_PREFIX = "sfc_"

_SECRET_BYTES = 32
_LOOKUP_BYTES = 9  # -> 18 hex chars
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _base64url(raw: bytes) -> str:
    """base64url with no padding — matches Node's `buf.toString('base64url')`."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def new_tenant_lookup_id() -> str:
    """18 hex chars. Non-secret. Never contains `_`."""
    return secrets.token_bytes(_LOOKUP_BYTES).hex()


@dataclass(frozen=True)
class GeneratedAccountToken:
    token: str
    """The full plaintext — shown to the user ONCE, never stored."""
    tenant_lookup_id: str
    """Non-secret; stored so cloud can look the tenant up."""
    secret: str
    """The secret half — what gets scrypt-hashed. Never stored in plaintext."""


def generate_account_token(tenant_lookup_id: str | None = None) -> GeneratedAccountToken:
    lookup = tenant_lookup_id if tenant_lookup_id is not None else new_tenant_lookup_id()
    secret = _base64url(secrets.token_bytes(_SECRET_BYTES))
    return GeneratedAccountToken(
        token=f"{ACCOUNT_TOKEN_PREFIX}{lookup}_{secret}",
        tenant_lookup_id=lookup,
        secret=secret,
    )


@dataclass(frozen=True)
class ParsedAccountToken:
    tenant_lookup_id: str
    secret: str


def parse_account_token(token: object) -> ParsedAccountToken | None:
    """Split a presented token into its non-secret lookup id and secret half.

    Returns None for ANY malformed token; verification then fails uniformly, so
    there is no oracle telling an attacker which half was wrong.
    """
    if not isinstance(token, str) or not token.startswith(ACCOUNT_TOKEN_PREFIX):
        return None
    rest = token[len(ACCOUNT_TOKEN_PREFIX) :]
    sep = rest.find("_")
    if sep <= 0 or sep >= len(rest) - 1:
        return None
    lookup = rest[:sep]
    secret = rest[sep + 1 :]
    if not _SEGMENT_RE.match(lookup) or not _SEGMENT_RE.match(secret):
        return None
    return ParsedAccountToken(tenant_lookup_id=lookup, secret=secret)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/tenants/test_token_format.py -q`
Expected: PASS — "9 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/tenants backend/tests/unit/tenants
git commit -m "feat: mint and parse sfc_ account tokens matching saiife-cloud's ids.ts"
```

---

### Task 18: scrypt account-secret hashing with timing equalization

**Files:**
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/tokens.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants/test_token_hashing.py`

**Interfaces:**
- Consumes: `app.tenants.tokens` module namespace.
- Produces: `SCRYPT_N = 16384`, `SCRYPT_R = 8`, `SCRYPT_P = 1`, `KEY_LEN = 32`, `SALT_LEN = 16`, `DUMMY_SALT`, `hash_account_secret(secret: str, pepper: str, salt: bytes | None = None) -> str`, `verify_account_secret(secret: str, pepper: str, stored: str) -> bool`, `equalize_timing(secret: str, pepper: str) -> None`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/tenants/test_token_hashing.py`:

```python
"""Hashing is pinned by saiife-cloud/packages/control-api/src/auth.ts.

The golden vector below was produced with BOTH Python's hashlib.scrypt and Node's
crypto.scryptSync and is byte-identical in each. If it fails, cloud will reject
every token hub issues.
"""
import base64
import hashlib

import pytest

from app.tenants import tokens

# pepper="test-pepper", secret="s3cret", salt = 16 bytes of 0x07
GOLDEN = (
    "scrypt$16384$8$1$BwcHBwcHBwcHBwcHBwcHBw==$"
    "mxQuZODDRxgYwpXcqbCDE3nCvTiE47xP78i9l3YCC5k="
)


def test_scrypt_parameters_match_cloud() -> None:
    assert tokens.SCRYPT_N == 16384
    assert tokens.SCRYPT_R == 8
    assert tokens.SCRYPT_P == 1
    assert tokens.KEY_LEN == 32
    assert tokens.SALT_LEN == 16
    assert tokens.DUMMY_SALT == bytes([7]) * 16


def test_golden_vector_matches_node_scrypt_byte_for_byte() -> None:
    got = tokens.hash_account_secret("s3cret", "test-pepper", salt=bytes([7]) * 16)
    assert got == GOLDEN


def test_stored_format_is_self_describing() -> None:
    stored = tokens.hash_account_secret("anything", "pep")
    parts = stored.split("$")
    assert parts[0] == "scrypt"
    assert parts[1:4] == ["16384", "8", "1"]
    assert len(base64.b64decode(parts[4])) == 16
    assert len(base64.b64decode(parts[5])) == 32


def test_password_side_is_pepper_colon_secret() -> None:
    """Cloud hashes `${pepper}:${secret}` — the colon is part of the contract."""
    salt = bytes(range(16))
    expected = hashlib.scrypt(
        b"pep:s3cret", salt=salt, n=16384, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024
    )
    stored = tokens.hash_account_secret("s3cret", "pep", salt=salt)
    assert stored.split("$")[5] == base64.b64encode(expected).decode()


def test_salt_is_random_per_call() -> None:
    a = tokens.hash_account_secret("same", "pep")
    b = tokens.hash_account_secret("same", "pep")
    assert a != b


def test_verify_accepts_the_right_secret() -> None:
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("s3cret", "pep", stored) is True


def test_verify_rejects_the_wrong_secret() -> None:
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("wrong", "pep", stored) is False


def test_verify_rejects_the_wrong_pepper() -> None:
    """A leak of the hash store alone must not yield usable tokens."""
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("s3cret", "other-pepper", stored) is False


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "garbage",
        "argon2id$16384$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$c2FsdA==",
        "scrypt$16384$8$1$c2FsdA==$aGFzaA==$extra",
    ],
)
def test_verify_rejects_malformed_stored_hashes_without_raising(stored: str) -> None:
    assert tokens.verify_account_secret("s3cret", "pep", stored) is False


def test_verify_rejects_a_hash_of_the_wrong_length() -> None:
    short = "scrypt$16384$8$1$" + base64.b64encode(bytes(16)).decode() + "$" + \
        base64.b64encode(bytes(8)).decode()
    assert tokens.verify_account_secret("s3cret", "pep", short) is False


def test_equalize_timing_does_real_scrypt_work_and_returns_none() -> None:
    """The unknown-lookup-id path must still burn a scrypt so it is not a timing
    oracle for 'does this tenant exist'."""
    assert tokens.equalize_timing("s3cret", "pep") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/tenants/test_token_hashing.py -q`
Expected: FAIL with "AttributeError: module 'app.tenants.tokens' has no attribute 'SCRYPT_N'"

- [ ] **Step 3: Write minimal implementation**

Append to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/tokens.py`:

```python
# --- hashing (pinned by saiife-cloud/packages/control-api/src/auth.ts) -------

import binascii  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
SALT_LEN = 16

# 128 * N * r = 16 MiB of scratch; give OpenSSL headroom above its 32 MiB default.
_MAXMEM = 64 * 1024 * 1024

# A fixed dummy salt so the unknown-tenant path still performs scrypt work and
# cannot be used as a timing oracle. Byte-identical to cloud's `DUMMY_SALT`.
DUMMY_SALT = bytes([7]) * SALT_LEN


def _scrypt(secret: str, pepper: str, salt: bytes) -> bytes:
    # The pepper is mixed into the PASSWORD side; the salt is per-tenant and is
    # stored alongside the hash. Matches Node: scryptSync(`${pepper}:${secret}`, ...).
    return hashlib.scrypt(
        f"{pepper}:{secret}".encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_LEN,
        maxmem=_MAXMEM,
    )


def hash_account_secret(secret: str, pepper: str, salt: bytes | None = None) -> str:
    """Hash a token's secret half FOR STORAGE.

    Returns the self-describing `scrypt$N$r$p$<saltB64>$<hashB64>` — never the
    plaintext. Used at issuance; the plaintext is shown once and discarded.
    """
    salt = salt if salt is not None else secrets.token_bytes(SALT_LEN)
    digest = _scrypt(secret, pepper, salt)
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_account_secret(secret: str, pepper: str, stored: str) -> bool:
    """Constant-time verify of a presented secret against a stored hash string."""
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
    except (ValueError, binascii.Error):
        return False
    if len(expected) != KEY_LEN:
        return False
    try:
        actual = hashlib.scrypt(
            f"{pepper}:{secret}".encode("utf-8"),
            salt=salt, n=n, r=r, p=p, dklen=KEY_LEN, maxmem=_MAXMEM,
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def equalize_timing(secret: str, pepper: str) -> None:
    """Burn one scrypt against the dummy salt so an unknown lookup id costs the
    same as a real verification. Never returns or logs anything."""
    _scrypt(secret, pepper, DUMMY_SALT)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/tenants/test_token_hashing.py -q`
Expected: PASS — "15 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/tenants/tokens.py backend/tests/unit/tenants/test_token_hashing.py
git commit -m "feat: scrypt account-secret hashing matching cloud byte-for-byte"
```

---

### Task 19: Billing, tenant and install models plus their migration

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/billing.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/tenant.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/install.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/versions/20260721_1300_billing_tenants_installs.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_migrations.py:11-19`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_billing_models.py`

**Interfaces:**
- Consumes: `app.db.base.Base`, `app.models.user.User`.
- Produces: `Subscription(id, user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, created_at, updated_at)`; `StripeEvent(event_id, event_type, received_at)`; `Tenant(id, user_id, subscription_id, cloud_tenant_id, tenant_lookup_id, account_token_hash, account_token_hash_algo, account_token_issued_at, created_at)`; `Install(id, user_id, name, created_at, last_seen_at)`; alembic revision `20260721_1300_billing_tenants_installs` with `down_revision = "20260721_1200_initial_auth"`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_billing_models.py`:

```python
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.billing import StripeEvent, Subscription
from app.models.install import Install
from app.models.tenant import Tenant
from app.models.user import User


async def _user() -> User:
    async with SessionLocal() as db:
        u = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.mark.asyncio
async def test_subscription_tenant_and_install_roundtrip() -> None:
    user = await _user()
    sub_id, tenant_id, install_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=sub_id,
                user_id=user.id,
                stripe_customer_id="cus_1",
                stripe_subscription_id="sub_1",
                status="active",
                current_period_end=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(
            Tenant(
                id=tenant_id,
                user_id=user.id,
                subscription_id=sub_id,
                cloud_tenant_id="t_abc",
                tenant_lookup_id="0123456789abcdef01",
                account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
                account_token_hash_algo="scrypt",
                account_token_issued_at=None,
            )
        )
        db.add(Install(id=install_id, user_id=user.id, name="Work laptop"))
        await db.commit()

    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        assert tenant is not None
        assert tenant.cloud_tenant_id == "t_abc"
        assert tenant.account_token_issued_at is None
        install = await db.scalar(select(Install).where(Install.id == install_id))
        assert install is not None
        assert install.name == "Work laptop"


@pytest.mark.asyncio
async def test_stripe_event_id_is_the_primary_key_so_replays_collide() -> None:
    async with SessionLocal() as db:
        db.add(StripeEvent(event_id="evt_1", event_type="checkout.session.completed"))
        await db.commit()

    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            db.add(StripeEvent(event_id="evt_1", event_type="checkout.session.completed"))
            await db.commit()


@pytest.mark.asyncio
async def test_one_subscription_per_user() -> None:
    user = await _user()
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=uuid.uuid4(), user_id=user.id,
                stripe_customer_id="cus_a", stripe_subscription_id="sub_a", status="active",
            )
        )
        await db.commit()
    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            db.add(
                Subscription(
                    id=uuid.uuid4(), user_id=user.id,
                    stripe_customer_id="cus_b", stripe_subscription_id="sub_b", status="active",
                )
            )
            await db.commit()
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_migrations.py:11-19` — extend `EXPECTED_TABLES` to:

```python
EXPECTED_TABLES = {
    "users",
    "sessions",
    "oauth_accounts",
    "email_verifications",
    "passkeys",
    "passkey_challenges",
    "auth_events",
    "subscriptions",
    "stripe_events",
    "tenants",
    "installs",
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_billing_models.py tests/integration/test_migrations.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.models.billing'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/billing.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Subscription(Base):
    """The authority on whether this account is entitled to a cloud tenant."""

    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # incomplete | active | past_due | canceled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="incomplete")
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StripeEvent(Base):
    """Webhook idempotency ledger. `event_id` is the PRIMARY KEY: a replayed
    Stripe delivery collides on insert, which is how we detect it."""

    __tablename__ = "stripe_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/tenant.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Tenant(Base):
    """Hub's record of a tenant that exists in saiife-cloud.

    `account_token_hash` is the ONLY account-token material stored anywhere in
    hub. The plaintext is shown once at issuance and never persisted or logged.
    `account_token_issued_at` is None while a token exists in cloud but has never
    been revealed to the user (the webhook-created first token), which is what
    the dashboard uses to prompt an issuance.
    """

    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    cloud_tenant_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    tenant_lookup_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    account_token_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    account_token_hash_algo: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scrypt"
    )
    account_token_issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/install.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Install(Base):
    """A desktop install the user has linked to this account."""

    __tablename__ = "installs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Replace `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/models/__init__.py`:

```python
"""Importing this package registers every table on `Base.metadata`."""

from . import billing, install, tenant, user  # noqa: F401

__all__ = ["billing", "install", "tenant", "user"]
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/alembic/versions/20260721_1300_billing_tenants_installs.py`:

```python
"""billing, tenants and installs

Revision ID: 20260721_1300_billing_tenants_installs
Revises: 20260721_1200_initial_auth
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260721_1300_billing_tenants_installs"
down_revision = "20260721_1200_initial_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("stripe_subscription_id", sa.String(length=80), nullable=True, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(length=80), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("cloud_tenant_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("tenant_lookup_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_token_hash", sa.Text(), nullable=False),
        sa.Column("account_token_hash_algo", sa.String(length=20), nullable=False),
        sa.Column("account_token_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "installs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("installs")
    op.drop_table("tenants")
    op.drop_table("stripe_events")
    op.drop_table("subscriptions")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_billing_models.py tests/integration/test_migrations.py -q`
Expected: PASS — "4 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/models backend/alembic/versions backend/tests/integration
git commit -m "feat: add subscription, stripe-event, tenant and install models with migration"
```

---

### Task 20: Stripe webhook signature verification

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/signature.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/test_signature.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SignatureError(Exception)` with a `.reason` attribute; `verify_stripe_signature(payload: bytes, header: str | None, secret: str, *, tolerance_seconds: int = 300, now: int | None = None) -> None` raising `SignatureError` on any failure.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/test_signature.py`:

```python
"""Stripe's `Stripe-Signature` scheme: t=<unix>,v1=<hex hmac-sha256 of "t.payload">.

The golden signature below was computed with the same HMAC Stripe uses.
"""
import hashlib
import hmac

import pytest

from app.billing.signature import SignatureError, verify_stripe_signature

PAYLOAD = b'{"id":"evt_test_1","type":"checkout.session.completed"}'
SECRET = "whsec_test_secret"
TS = 1750000000
GOLDEN_HEADER = (
    "t=1750000000,"
    "v1=038b44452344cb66f6b4328b0ef62957e8fbc2dd84284365b2cbe32d49d81305"
)


def _sign(payload: bytes, secret: str, ts: int) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def test_accepts_a_valid_signature() -> None:
    verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, now=TS)


def test_golden_header_matches_a_freshly_computed_one() -> None:
    assert _sign(PAYLOAD, SECRET, TS) == GOLDEN_HEADER


def test_rejects_a_missing_header() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, None, SECRET, now=TS)
    assert exc.value.reason == "missing_signature_header"


def test_rejects_a_malformed_header() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, "not-a-signature", SECRET, now=TS)
    assert exc.value.reason == "malformed_signature_header"


def test_rejects_a_tampered_payload() -> None:
    tampered = PAYLOAD.replace(b"evt_test_1", b"evt_test_2")
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(tampered, GOLDEN_HEADER, SECRET, now=TS)
    assert exc.value.reason == "signature_mismatch"


def test_rejects_the_wrong_secret() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, "whsec_other", now=TS)
    assert exc.value.reason == "signature_mismatch"


def test_rejects_a_stale_timestamp_outside_the_tolerance() -> None:
    """Replay defence: an old, otherwise-valid signature is refused."""
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS + 301)
    assert exc.value.reason == "timestamp_outside_tolerance"


def test_rejects_a_future_timestamp_outside_the_tolerance() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS - 301)
    assert exc.value.reason == "timestamp_outside_tolerance"


def test_accepts_a_timestamp_at_the_edge_of_the_tolerance() -> None:
    verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS + 300)


def test_accepts_a_header_carrying_multiple_v1_signatures() -> None:
    """Stripe sends several v1 values during secret rotation; any match is valid."""
    header = GOLDEN_HEADER + ",v1=" + "0" * 64
    verify_stripe_signature(PAYLOAD, header, SECRET, now=TS)


def test_rejects_a_header_with_only_unknown_schemes() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, f"t={TS},v0=deadbeef", SECRET, now=TS)
    assert exc.value.reason == "malformed_signature_header"


def test_rejects_an_empty_secret() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, "", now=TS)
    assert exc.value.reason == "webhook_secret_not_configured"
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/billing/test_signature.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.billing'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/signature.py`:

```python
"""Stripe webhook signature verification.

Implemented here rather than via the SDK so it is deterministic, offline-testable,
and pinned: NO state changes until this passes. Stripe's scheme is
`Stripe-Signature: t=<unix>,v1=<hex>` where the MAC is HMAC-SHA256 over the exact
bytes `f"{t}.".encode() + raw_body` — the RAW body, never a re-serialized dict.
"""
from __future__ import annotations

import hashlib
import hmac
import time


class SignatureError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


def _parse_header(header: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None, []
        elif key == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def verify_stripe_signature(
    payload: bytes,
    header: str | None,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    """Raise `SignatureError` unless `header` authenticates `payload`."""
    if not secret:
        raise SignatureError(
            "webhook_secret_not_configured", "no Stripe webhook secret is configured"
        )
    if not header:
        raise SignatureError("missing_signature_header", "no Stripe-Signature header")

    timestamp, signatures = _parse_header(header)
    if timestamp is None or not signatures:
        raise SignatureError(
            "malformed_signature_header", "header carried no usable t/v1 pair"
        )

    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise SignatureError(
            "timestamp_outside_tolerance",
            f"signature timestamp is {abs(current - timestamp)}s away from now",
        )

    expected = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise SignatureError("signature_mismatch", "no v1 signature matched the payload")
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/billing/test_signature.py -q`
Expected: PASS — "12 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/billing backend/tests/unit/billing
git commit -m "feat: verify Stripe webhook signatures with timestamp tolerance"
```

---

### Task 21: StripeGateway seam — mock and live

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/gateway.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/test_gateway.py`

**Interfaces:**
- Consumes: `settings.STRIPE_SECRET_KEY`, `settings.STRIPE_PRICE_ID`, `settings.APP_URL`.
- Produces: `CheckoutSession(id, url, customer_id)`; `PortalSession(url)`; protocol `StripeGateway` with `async create_checkout_session(*, user_id: str, email: str, price_id: str, success_url: str, cancel_url: str) -> CheckoutSession` and `async create_portal_session(*, customer_id: str, return_url: str) -> PortalSession`; `MockStripeGateway`; `LiveStripeGateway`; `get_stripe_gateway()`; `set_stripe_gateway()`; `configure_default_stripe_gateway()`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/test_gateway.py`:

```python
import pytest

from app.billing.gateway import (
    MockStripeGateway,
    configure_default_stripe_gateway,
    get_stripe_gateway,
    set_stripe_gateway,
)


@pytest.mark.asyncio
async def test_mock_checkout_session_is_deterministic_and_records_the_call() -> None:
    gw = MockStripeGateway()
    session = await gw.create_checkout_session(
        user_id="11111111-1111-1111-1111-111111111111",
        email="alice@example.com",
        price_id="price_test",
        success_url="https://app.example.invalid/billing?ok=1",
        cancel_url="https://app.example.invalid/billing?cancelled=1",
    )
    assert session.id == "cs_mock_1"
    assert session.customer_id == "cus_mock_1"
    assert session.url == "https://checkout.stripe.invalid/mock/cs_mock_1"
    assert gw.checkout_calls[0]["email"] == "alice@example.com"
    assert gw.checkout_calls[0]["price_id"] == "price_test"


@pytest.mark.asyncio
async def test_mock_ids_increment_per_call() -> None:
    gw = MockStripeGateway()
    first = await gw.create_checkout_session(
        user_id="u", email="a@example.com", price_id="p",
        success_url="https://x.invalid", cancel_url="https://x.invalid",
    )
    second = await gw.create_checkout_session(
        user_id="u", email="a@example.com", price_id="p",
        success_url="https://x.invalid", cancel_url="https://x.invalid",
    )
    assert (first.id, second.id) == ("cs_mock_1", "cs_mock_2")


@pytest.mark.asyncio
async def test_mock_portal_session_returns_a_url_and_records_the_call() -> None:
    gw = MockStripeGateway()
    portal = await gw.create_portal_session(
        customer_id="cus_mock_1", return_url="https://app.example.invalid/billing"
    )
    assert portal.url == "https://billing.stripe.invalid/mock/cus_mock_1"
    assert gw.portal_calls == [
        {"customer_id": "cus_mock_1", "return_url": "https://app.example.invalid/billing"}
    ]


def test_default_gateway_is_the_mock_without_a_secret_key() -> None:
    configure_default_stripe_gateway()
    assert isinstance(get_stripe_gateway(), MockStripeGateway)


def test_set_gateway_replaces_the_active_gateway() -> None:
    replacement = MockStripeGateway()
    set_stripe_gateway(replacement)
    assert get_stripe_gateway() is replacement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/billing/test_gateway.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.billing.gateway'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/gateway.py`:

```python
"""Stripe API access behind a seam so every test runs offline.

Only OUTBOUND calls live here. Inbound webhooks are verified by
`app.billing.signature` and applied by `app.billing.service`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..core.config import settings


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str
    customer_id: str


@dataclass(frozen=True)
class PortalSession:
    url: str


class StripeGateway(Protocol):
    async def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession: ...


class MockStripeGateway:
    """Deterministic, inspectable, and never touches the network."""

    def __init__(self) -> None:
        self.checkout_calls: list[dict[str, Any]] = []
        self.portal_calls: list[dict[str, Any]] = []
        self._counter = 0

    async def create_checkout_session(
        self, *, user_id: str, email: str, price_id: str, success_url: str, cancel_url: str
    ) -> CheckoutSession:
        self._counter += 1
        n = self._counter
        self.checkout_calls.append(
            {
                "user_id": user_id,
                "email": email,
                "price_id": price_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
        )
        return CheckoutSession(
            id=f"cs_mock_{n}",
            url=f"https://checkout.stripe.invalid/mock/cs_mock_{n}",
            customer_id=f"cus_mock_{n}",
        )

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession:
        self.portal_calls.append({"customer_id": customer_id, "return_url": return_url})
        return PortalSession(url=f"https://billing.stripe.invalid/mock/{customer_id}")


class LiveStripeGateway:
    """The real Stripe transport. Constructed only when a secret key is set."""

    def __init__(self, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("LiveStripeGateway requires a Stripe secret key.")
        import stripe

        self._stripe = stripe
        self._client = stripe.StripeClient(secret_key)

    async def create_checkout_session(
        self, *, user_id: str, email: str, price_id: str, success_url: str, cancel_url: str
    ) -> CheckoutSession:
        session = self._client.checkout.sessions.create(
            params={
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "customer_email": email,
                "client_reference_id": user_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                # Echoed back on the webhook so the handler can find the user
                # without trusting anything else in the payload.
                "metadata": {"hub_user_id": user_id},
                "subscription_data": {"metadata": {"hub_user_id": user_id}},
            }
        )
        customer = session.customer
        customer_id = customer if isinstance(customer, str) else getattr(customer, "id", "")
        return CheckoutSession(id=session.id, url=session.url or "", customer_id=customer_id or "")

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession:
        session = self._client.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url}
        )
        return PortalSession(url=session.url)


_gateway: StripeGateway = MockStripeGateway()


def get_stripe_gateway() -> StripeGateway:
    return _gateway


def set_stripe_gateway(g: StripeGateway) -> None:
    global _gateway
    _gateway = g


def configure_default_stripe_gateway() -> None:
    if settings.STRIPE_SECRET_KEY:
        set_stripe_gateway(LiveStripeGateway(settings.STRIPE_SECRET_KEY))
    else:
        set_stripe_gateway(MockStripeGateway())
```

Note: the test conftest sets `STRIPE_SECRET_KEY=sk_test_not_a_real_key`, so
`test_default_gateway_is_the_mock_without_a_secret_key` must run with it cleared.
Add this fixture to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/unit/billing/test_gateway.py` at the top of the file, right after the imports:

```python
@pytest.fixture(autouse=True)
def _no_stripe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/unit/billing/test_gateway.py -q`
Expected: PASS — "5 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/billing/gateway.py backend/tests/unit/billing/test_gateway.py
git commit -m "feat: add StripeGateway seam with offline mock and live transport"
```

---

### Task 22: Billing service — subscription state transitions

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/service.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/service.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_service.py`

**Interfaces:**
- Consumes: `app.models.billing.Subscription`, `app.models.tenant.Tenant`, `app.cloud.seam.CloudControlPlane`, `app.tenants.tokens`.
- Produces:
  - `app.tenants.service.ensure_tenant(db, cloud, *, subscription, pepper) -> Tenant` — idempotent; reuses the existing hub Tenant row and calls `create_tenant` at most once per subscription.
  - `app.tenants.service.issue_account_token(db, cloud, *, subscription, pepper) -> IssuedAccountToken` where `IssuedAccountToken(token, cloud_tenant_id, issued_at)` — mints, hashes, rotates in cloud, stamps `account_token_issued_at`.
  - `app.tenants.service.remove_tenant(db, cloud, *, subscription) -> None` — idempotent.
  - `app.billing.service.apply_stripe_event(db, cloud, *, event: dict, pepper) -> str` returning the applied action name.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_service.py`:

```python
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.billing.service import apply_stripe_event
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.tenants.service import ensure_tenant, issue_account_token, remove_tenant
from app.tenants.tokens import parse_account_token, verify_account_secret

PEPPER = "test-pepper"


async def _user_and_subscription(status: str = "active") -> tuple[User, Subscription]:
    async with SessionLocal() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user.id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status=status,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(user)
        await db.refresh(sub)
        return user, sub


@pytest.mark.asyncio
async def test_ensure_tenant_creates_exactly_one_tenant() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        tenant = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    assert tenant.cloud_tenant_id.startswith("t_")
    assert tenant.account_token_issued_at is None
    assert len(cloud.create_calls) == 1
    assert cloud.create_calls[0].external_ref == f"hub:{sub.stripe_subscription_id}"


@pytest.mark.asyncio
async def test_ensure_tenant_is_idempotent_and_does_not_call_cloud_twice() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        first = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        second = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    assert first.cloud_tenant_id == second.cloud_tenant_id
    assert len(cloud.create_calls) == 1
    async with SessionLocal() as db:
        rows = (await db.execute(select(Tenant))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_issue_account_token_returns_a_verifiable_token_and_stores_only_the_hash() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        issued = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()

    parsed = parse_account_token(issued.token)
    assert parsed is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert tenant.tenant_lookup_id == parsed.tenant_lookup_id
    assert tenant.account_token_issued_at is not None
    assert verify_account_secret(parsed.secret, PEPPER, tenant.account_token_hash) is True
    # The plaintext is nowhere in the stored row.
    assert issued.token not in tenant.account_token_hash
    assert parsed.secret not in tenant.account_token_hash


@pytest.mark.asyncio
async def test_issuing_twice_rotates_and_invalidates_the_previous_token() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        first = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        second = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()

    assert first.token != second.token
    assert first.cloud_tenant_id == second.cloud_tenant_id
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    old = parse_account_token(first.token)
    new = parse_account_token(second.token)
    assert old is not None and new is not None
    assert verify_account_secret(old.secret, PEPPER, tenant.account_token_hash) is False
    assert verify_account_secret(new.secret, PEPPER, tenant.account_token_hash) is True


@pytest.mark.asyncio
async def test_remove_tenant_deletes_in_cloud_and_locally_and_is_idempotent() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        tenant = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
        cloud_tenant_id = tenant.cloud_tenant_id
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await remove_tenant(db, cloud, subscription=sub)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await remove_tenant(db, cloud, subscription=sub)  # no raise
        await db.commit()

    assert cloud.delete_calls == [cloud_tenant_id]
    assert cloud.tenants == {}
    async with SessionLocal() as db:
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_checkout_completed_activates_the_subscription_and_creates_a_tenant() -> None:
    user, sub = await _user_and_subscription(status="incomplete")
    cloud = InMemoryCloudControlPlane()
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": sub.stripe_customer_id,
                "subscription": sub.stripe_subscription_id,
                "metadata": {"hub_user_id": str(user.id)},
            }
        },
    }
    async with SessionLocal() as db:
        action = await apply_stripe_event(db, cloud, event=event, pepper=PEPPER)
        await db.commit()
    assert action == "tenant_created"
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert stored is not None and stored.status == "active"
    assert tenant is not None
    assert len(cloud.create_calls) == 1


@pytest.mark.asyncio
async def test_subscription_deleted_cancels_and_removes_the_tenant() -> None:
    user, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        merged = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=merged, pepper=PEPPER)
        await db.commit()
    event = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": sub.stripe_subscription_id, "customer": sub.stripe_customer_id}},
    }
    async with SessionLocal() as db:
        action = await apply_stripe_event(db, cloud, event=event, pepper=PEPPER)
        await db.commit()
    assert action == "tenant_deleted"
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        assert stored is not None and stored.status == "canceled"
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_unhandled_event_type_is_a_no_op() -> None:
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        action = await apply_stripe_event(
            db, cloud, event={"id": "evt_3", "type": "invoice.created", "data": {"object": {}}},
            pepper=PEPPER,
        )
        await db.commit()
    assert action == "ignored"
    assert cloud.create_calls == []
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_service.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.billing.service'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/service.py`:

```python
"""Tenant lifecycle against saiife-cloud.

Never say "provision" here — cloud already uses that word for Pub/Sub subscription
provisioning. Tenant lifecycle is create / delete.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cloud.contracts import CreateTenantRequest
from ..cloud.seam import CloudControlPlane
from ..models.billing import Subscription
from ..models.tenant import Tenant
from . import tokens

log = structlog.get_logger(__name__)


def external_ref(subscription: Subscription) -> str:
    """The idempotency key cloud dedupes on. Stable for the subscription's life."""
    return f"hub:{subscription.stripe_subscription_id or subscription.id}"


@dataclass(frozen=True)
class IssuedAccountToken:
    token: str
    """PLAINTEXT — returned to the user exactly once. Never logged or persisted."""
    cloud_tenant_id: str
    issued_at: datetime


async def _load_tenant(db: AsyncSession, subscription: Subscription) -> Tenant | None:
    return await db.scalar(select(Tenant).where(Tenant.subscription_id == subscription.id))


async def ensure_tenant(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    subscription: Subscription,
    pepper: str,
) -> Tenant:
    """Create the cloud tenant for this subscription if it does not exist yet.

    Idempotent at BOTH layers: hub short-circuits on the existing Tenant row, and
    cloud dedupes on `externalRef`. A Stripe retry therefore cannot double-create.

    The first account token is minted here so the tenant is never tokenless, but
    its plaintext is discarded — the user reveals a token via `issue_account_token`.
    """
    existing = await _load_tenant(db, subscription)
    if existing is not None:
        return existing

    generated = tokens.generate_account_token()
    token_hash = tokens.hash_account_secret(generated.secret, pepper)
    cloud_tenant = await cloud.create_tenant(
        CreateTenantRequest(
            external_ref=external_ref(subscription),
            tenant_lookup_id=generated.tenant_lookup_id,
            account_token_hash=token_hash,
        )
    )
    tenant = Tenant(
        id=uuid.uuid4(),
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        cloud_tenant_id=cloud_tenant.tenant_id,
        tenant_lookup_id=generated.tenant_lookup_id,
        account_token_hash=token_hash,
        account_token_hash_algo="scrypt",
        account_token_issued_at=None,
    )
    db.add(tenant)
    await db.flush()
    # NEVER log the token or the secret — only that a tenant now exists.
    log.info("tenant_created", cloud_tenant_id=cloud_tenant.tenant_id)
    return tenant


async def issue_account_token(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    subscription: Subscription,
    pepper: str,
) -> IssuedAccountToken:
    """Mint a NEW account token, replace the stored hash, return the plaintext once.

    Calling this a second time is rotation: the previous token stops verifying the
    moment the new hash lands.
    """
    tenant = await ensure_tenant(db, cloud, subscription=subscription, pepper=pepper)

    generated = tokens.generate_account_token()
    token_hash = tokens.hash_account_secret(generated.secret, pepper)
    await cloud.create_tenant(
        CreateTenantRequest(
            external_ref=external_ref(subscription),
            tenant_lookup_id=generated.tenant_lookup_id,
            account_token_hash=token_hash,
        )
    )
    tenant.tenant_lookup_id = generated.tenant_lookup_id
    tenant.account_token_hash = token_hash
    tenant.account_token_hash_algo = "scrypt"
    tenant.account_token_issued_at = datetime.now(timezone.utc)
    await db.flush()
    log.info("account_token_issued", cloud_tenant_id=tenant.cloud_tenant_id)
    return IssuedAccountToken(
        token=generated.token,
        cloud_tenant_id=tenant.cloud_tenant_id,
        issued_at=tenant.account_token_issued_at,
    )


async def remove_tenant(
    db: AsyncSession, cloud: CloudControlPlane, *, subscription: Subscription
) -> None:
    """Delete the cloud tenant and hub's record of it. Idempotent."""
    tenant = await _load_tenant(db, subscription)
    if tenant is None:
        return
    await cloud.delete_tenant(tenant.cloud_tenant_id)
    await db.delete(tenant)
    await db.flush()
    log.info("tenant_deleted", cloud_tenant_id=tenant.cloud_tenant_id)
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/service.py`:

```python
"""Applies a VERIFIED Stripe event to subscription and tenant state.

The caller must have verified the signature and rejected replays before calling
this. Nothing here re-checks authenticity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cloud.seam import CloudControlPlane
from ..models.billing import Subscription
from ..tenants.service import ensure_tenant, remove_tenant

log = structlog.get_logger(__name__)


async def _find_subscription(
    db: AsyncSession, obj: dict[str, Any]
) -> Subscription | None:
    """Locate the hub subscription from a Stripe object, most specific first."""
    stripe_subscription_id = obj.get("subscription") or obj.get("id")
    if isinstance(stripe_subscription_id, str):
        found = await db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        if found is not None:
            return found
    customer = obj.get("customer")
    if isinstance(customer, str):
        return await db.scalar(
            select(Subscription).where(Subscription.stripe_customer_id == customer)
        )
    return None


def _period_end(obj: dict[str, Any]) -> datetime | None:
    raw = obj.get("current_period_end")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    return None


async def apply_stripe_event(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    event: dict[str, Any],
    pepper: str,
) -> str:
    """Return the action taken: tenant_created | tenant_deleted | subscription_updated
    | unknown_subscription | ignored."""
    event_type = str(event.get("type", ""))
    obj = event.get("data", {}).get("object", {})
    if not isinstance(obj, dict):
        return "ignored"

    if event_type == "checkout.session.completed":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            log.warning("stripe_event_unknown_subscription", event_type=event_type)
            return "unknown_subscription"
        stripe_subscription_id = obj.get("subscription")
        if isinstance(stripe_subscription_id, str):
            subscription.stripe_subscription_id = stripe_subscription_id
        subscription.status = "active"
        subscription.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await ensure_tenant(db, cloud, subscription=subscription, pepper=pepper)
        return "tenant_created"

    if event_type == "customer.subscription.deleted":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            log.warning("stripe_event_unknown_subscription", event_type=event_type)
            return "unknown_subscription"
        subscription.status = "canceled"
        subscription.updated_at = datetime.now(timezone.utc)
        await remove_tenant(db, cloud, subscription=subscription)
        return "tenant_deleted"

    if event_type == "customer.subscription.updated":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            return "unknown_subscription"
        status = obj.get("status")
        if isinstance(status, str):
            subscription.status = "active" if status in {"active", "trialing"} else status
        subscription.current_period_end = _period_end(obj) or subscription.current_period_end
        subscription.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return "subscription_updated"

    return "ignored"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_service.py -q`
Expected: PASS — "8 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/tenants/service.py backend/src/app/billing/service.py backend/tests/integration/billing
git commit -m "feat: tenant lifecycle service and Stripe-driven subscription transitions"
```

---

### Task 23: Billing routes — checkout, portal, subscription status

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/routes.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_routes.py`

**Interfaces:**
- Consumes: `app.auth.deps.verified_user`, `app.billing.gateway.get_stripe_gateway`, `app.models.billing.Subscription`, `app.models.tenant.Tenant`, `settings.STRIPE_PRICE_ID`, `settings.APP_URL`.
- Produces: `POST /api/v1/billing/checkout-session -> {"url": str}`; `POST /api/v1/billing/portal-session -> {"url": str}`; `GET /api/v1/billing/subscription -> {"status": str, "current_period_end": str | None, "has_tenant": bool, "account_token_issued_at": str | None}`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_routes.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.billing.gateway import MockStripeGateway, set_stripe_gateway
from app.db.session import SessionLocal
from app.models.billing import Subscription


@pytest.fixture(autouse=True)
def mock_gateway() -> MockStripeGateway:
    gw = MockStripeGateway()
    set_stripe_gateway(gw)
    return gw


@pytest.mark.asyncio
async def test_subscription_status_is_none_before_subscribing(client, signed_in_user) -> None:
    r = await client.get("/api/v1/billing/subscription", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == {
        "status": "none",
        "current_period_end": None,
        "has_tenant": False,
        "account_token_issued_at": None,
    }


@pytest.mark.asyncio
async def test_checkout_session_requires_authentication(client) -> None:
    r = await client.post("/api/v1/billing/checkout-session", headers={"X-CSRF-Token": "x"},
                          cookies={"csrf_token": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkout_session_returns_a_url_and_records_the_subscription(
    client, signed_in_user, mock_gateway
) -> None:
    r = await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    assert r.json()["url"] == "https://checkout.stripe.invalid/mock/cs_mock_1"
    assert mock_gateway.checkout_calls[0]["email"] == signed_in_user["user"].email

    async with SessionLocal() as db:
        sub = await db.scalar(
            select(Subscription).where(Subscription.user_id == signed_in_user["user"].id)
        )
    assert sub is not None
    assert sub.status == "incomplete"
    assert sub.stripe_customer_id == "cus_mock_1"


@pytest.mark.asyncio
async def test_checkout_session_reuses_an_existing_customer(
    client, signed_in_user, mock_gateway
) -> None:
    await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Subscription).where(Subscription.user_id == signed_in_user["user"].id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].stripe_customer_id == "cus_mock_1"


@pytest.mark.asyncio
async def test_portal_session_requires_an_existing_customer(client, signed_in_user) -> None:
    r = await client.post(
        "/api/v1/billing/portal-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_subscription"


@pytest.mark.asyncio
async def test_portal_session_returns_a_url(client, signed_in_user, mock_gateway) -> None:
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=uuid.uuid4(),
                user_id=signed_in_user["user"].id,
                stripe_customer_id="cus_existing",
                stripe_subscription_id="sub_existing",
                status="active",
            )
        )
        await db.commit()
    r = await client.post(
        "/api/v1/billing/portal-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    assert r.json()["url"] == "https://billing.stripe.invalid/mock/cus_existing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_routes.py -q`
Expected: FAIL with "assert 404 == 200" (no `/api/v1/billing/subscription` route exists)

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/routes.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..core.config import settings
from ..core.rate_limit import limiter
from ..db.session import get_db
from ..models.billing import Subscription
from ..models.tenant import Tenant
from ..models.user import User
from .gateway import get_stripe_gateway

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None:
        return {
            "status": "none",
            "current_period_end": None,
            "has_tenant": False,
            "account_token_issued_at": None,
        }
    tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == subscription.id))
    return {
        "status": subscription.status,
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription.current_period_end
            else None
        ),
        "has_tenant": tenant is not None,
        "account_token_issued_at": (
            tenant.account_token_issued_at.isoformat()
            if tenant is not None and tenant.account_token_issued_at
            else None
        ),
    }


@router.post("/checkout-session")
@limiter.limit("10/minute")
async def create_checkout_session(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    session = await get_stripe_gateway().create_checkout_session(
        user_id=str(user.id),
        email=user.email,
        price_id=settings.STRIPE_PRICE_ID,
        success_url=f"{settings.APP_URL}/dashboard?subscribed=1",
        cancel_url=f"{settings.APP_URL}/billing?cancelled=1",
    )
    if subscription is None:
        db.add(
            Subscription(
                id=uuid.uuid4(),
                user_id=user.id,
                stripe_customer_id=session.customer_id,
                stripe_subscription_id=None,
                status="incomplete",
            )
        )
        await db.commit()
    return {"url": session.url}


@router.post("/portal-session")
@limiter.limit("10/minute")
async def create_portal_session(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None:
        raise _err("no_subscription", "You do not have a subscription yet.", 404)
    portal = await get_stripe_gateway().create_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.APP_URL}/billing",
    )
    return {"url": portal.url}
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — extend the deferred import block and the lifespan:

```python
from .billing.gateway import configure_default_stripe_gateway
from .cloud.deps import configure_default_cloud
```

```python
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_default_mailer()
    configure_default_cloud()
    configure_default_stripe_gateway()
    yield
```

```python
from app.api.v1.auth.router import router as auth_router  # noqa: E402
from app.api.v1.health.router import router as health_router  # noqa: E402
from app.billing.routes import router as billing_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(billing_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_routes.py -q`
Expected: PASS — "6 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/billing/routes.py backend/src/app/main.py backend/tests/integration/billing/test_routes.py
git commit -m "feat: add billing checkout, portal and subscription-status routes"
```

---

### Task 24: The Stripe webhook — signature-verified and idempotent

**Files:**
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/routes.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_webhook.py`

**Interfaces:**
- Consumes: `app.billing.signature.verify_stripe_signature`, `app.billing.service.apply_stripe_event`, `app.cloud.deps.get_cloud`, `app.models.billing.StripeEvent`, `settings.STRIPE_WEBHOOK_SECRET`, `settings.STRIPE_SIGNATURE_TOLERANCE_SECONDS`, `settings.ACCOUNT_TOKEN_PEPPER`.
- Produces: `POST /api/v1/billing/webhook` returning `200 {"received": true, "duplicate": bool, "action": str}`, or `400 {"error": {"code": "invalid_signature", ...}}`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/billing/test_webhook.py`:

```python
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.cloud.deps import set_cloud
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import StripeEvent, Subscription
from app.models.tenant import Tenant
from app.models.user import User

SECRET = "whsec_test_secret"


def _sign(body: bytes, ts: int | None = None) -> dict[str, str]:
    ts = ts if ts is not None else int(time.time())
    mac = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return {"Stripe-Signature": f"t={ts},v1={mac.hexdigest()}"}


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _seed_incomplete_subscription() -> tuple[User, Subscription]:
    async with SessionLocal() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user.id,
            stripe_customer_id="cus_hook",
            stripe_subscription_id=None,
            status="incomplete",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(user)
        await db.refresh(sub)
        return user, sub


def _checkout_event(user: User, event_id: str = "evt_hook_1") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_hook",
                    "subscription": "sub_hook",
                    "metadata": {"hub_user_id": str(user.id)},
                }
            },
        }
    ).encode()


@pytest.mark.asyncio
async def test_webhook_rejects_a_missing_signature(client, cloud) -> None:
    r = await client.post("/api/v1/billing/webhook", content=b'{"id":"evt_x","type":"ping"}')
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_rejects_a_tampered_body(client, cloud) -> None:
    body = b'{"id":"evt_x","type":"ping"}'
    headers = _sign(body)
    r = await client.post(
        "/api/v1/billing/webhook", content=b'{"id":"evt_y","type":"ping"}', headers=headers
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_rejects_a_stale_signature(client, cloud) -> None:
    body = b'{"id":"evt_x","type":"ping"}'
    stale = int(time.time()) - 3600
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body, stale))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_makes_no_state_change_when_the_signature_fails(client, cloud) -> None:
    user, _ = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    r = await client.post(
        "/api/v1/billing/webhook", content=body, headers={"Stripe-Signature": "t=1,v1=deadbeef"}
    )
    assert r.status_code == 400
    assert cloud.create_calls == []
    async with SessionLocal() as db:
        assert (await db.execute(select(Tenant))).scalars().all() == []
        assert (await db.execute(select(StripeEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_valid_checkout_completed_creates_exactly_one_tenant(client, cloud) -> None:
    user, sub = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert r.status_code == 200
    assert r.json() == {"received": True, "duplicate": False, "action": "tenant_created"}
    assert len(cloud.create_calls) == 1
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert stored is not None and stored.status == "active"
    assert stored.stripe_subscription_id == "sub_hook"
    assert tenant is not None


@pytest.mark.asyncio
async def test_replaying_the_same_event_id_is_a_no_op(client, cloud) -> None:
    """Stripe retries. The second delivery must change nothing at all."""
    user, sub = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    first = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert first.json()["duplicate"] is False

    second = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert second.status_code == 200
    assert second.json() == {"received": True, "duplicate": True, "action": "ignored"}

    assert len(cloud.create_calls) == 1
    assert len(cloud.tenants) == 1
    async with SessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        events = (await db.execute(select(StripeEvent))).scalars().all()
    assert len(tenants) == 1
    assert len(events) == 1


@pytest.mark.asyncio
async def test_a_second_distinct_event_id_for_the_same_subscription_still_creates_one_tenant(
    client, cloud
) -> None:
    """Belt and braces: even if Stripe sends a NEW event id for the same checkout,
    tenant creation is idempotent at the service and contract layers."""
    user, _ = await _seed_incomplete_subscription()
    body_a = _checkout_event(user, event_id="evt_hook_a")
    body_b = _checkout_event(user, event_id="evt_hook_b")
    await client.post("/api/v1/billing/webhook", content=body_a, headers=_sign(body_a))
    await client.post("/api/v1/billing/webhook", content=body_b, headers=_sign(body_b))
    assert len(cloud.tenants) == 1
    async with SessionLocal() as db:
        assert len((await db.execute(select(Tenant))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_subscription_deleted_removes_the_tenant_and_is_replay_safe(client, cloud) -> None:
    user, sub = await _seed_incomplete_subscription()
    created = _checkout_event(user)
    await client.post("/api/v1/billing/webhook", content=created, headers=_sign(created))

    deleted = json.dumps(
        {
            "id": "evt_hook_del",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_hook", "customer": "cus_hook"}},
        }
    ).encode()
    r1 = await client.post("/api/v1/billing/webhook", content=deleted, headers=_sign(deleted))
    assert r1.json()["action"] == "tenant_deleted"
    r2 = await client.post("/api/v1/billing/webhook", content=deleted, headers=_sign(deleted))
    assert r2.json() == {"received": True, "duplicate": True, "action": "ignored"}

    assert len(cloud.delete_calls) == 1
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        assert stored is not None and stored.status == "canceled"
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_unhandled_event_type_is_recorded_but_changes_nothing(client, cloud) -> None:
    body = json.dumps(
        {"id": "evt_ignored", "type": "invoice.created", "data": {"object": {}}}
    ).encode()
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert r.status_code == 200
    assert r.json() == {"received": True, "duplicate": False, "action": "ignored"}
    assert cloud.create_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_webhook.py -q`
Expected: FAIL with "assert 404 == 400" (no `/api/v1/billing/webhook` route exists)

- [ ] **Step 3: Write minimal implementation**

Add to `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/billing/routes.py` — new imports, and extend the existing `from ..models.billing import Subscription` line to `from ..models.billing import StripeEvent, Subscription` so there is exactly one import per module:

```python
import json

import structlog
from sqlalchemy.exc import IntegrityError

from ..cloud.deps import get_cloud
from ..models.billing import StripeEvent, Subscription
from .service import apply_stripe_event
from .signature import SignatureError, verify_stripe_signature

log = structlog.get_logger(__name__)
```

and the handler at the end of the file:

```python
@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Signature-verified, replay-safe entry point for Stripe.

    Order is load-bearing:
      1. verify the signature over the RAW bytes — no state change before this;
      2. claim the event id (PK insert) — a replay collides and short-circuits;
      3. apply the event.
    """
    raw = await request.body()
    try:
        verify_stripe_signature(
            raw,
            request.headers.get("stripe-signature"),
            settings.STRIPE_WEBHOOK_SECRET,
            tolerance_seconds=settings.STRIPE_SIGNATURE_TOLERANCE_SECONDS,
        )
    except SignatureError as exc:
        # Never echo the reason to the caller — log it, return one flat code.
        log.warning("stripe_webhook_rejected", reason=exc.reason)
        raise _err("invalid_signature", "Signature verification failed.", 400) from None

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        raise _err("invalid_payload", "Webhook body was not JSON.", 400) from None
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise _err("invalid_payload", "Webhook body had no event id.", 400)

    event_id = event["id"]
    event_type = str(event.get("type", ""))

    # Claim the event id first. A retried delivery collides on the primary key,
    # which is exactly how we detect a replay.
    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        log.info("stripe_webhook_replay", event_id=event_id, event_type=event_type)
        return {"received": True, "duplicate": True, "action": "ignored"}

    action = await apply_stripe_event(
        db, get_cloud(), event=event, pepper=settings.ACCOUNT_TOKEN_PEPPER
    )
    await db.commit()
    log.info("stripe_webhook_applied", event_id=event_id, event_type=event_type, action=action)
    return {"received": True, "duplicate": False, "action": action}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/billing/test_webhook.py -q`
Expected: PASS — "9 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/billing/routes.py backend/tests/integration/billing/test_webhook.py
git commit -m "feat: signature-verified, replay-safe Stripe webhook handler"
```

---

### Task 25: Tenant routes — issue and rotate the account token

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/routes.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/tenants/test_routes.py`

**Interfaces:**
- Consumes: `app.auth.deps.verified_user`, `app.tenants.service.issue_account_token`, `app.cloud.deps.get_cloud`, `app.models.billing.Subscription`, `app.models.tenant.Tenant`.
- Produces: `POST /api/v1/tenants/account-token -> 201 {"token": str, "cloud_tenant_id": str, "issued_at": str}`; `GET /api/v1/tenants/me -> {"cloud_tenant_id": str, "tenant_lookup_id": str, "account_token_issued_at": str | None}` or `404 no_tenant`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/tenants/test_routes.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.cloud.deps import set_cloud
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant
from app.tenants.tokens import parse_account_token, verify_account_secret

PEPPER = "test-pepper"


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _active_subscription(user_id: uuid.UUID) -> Subscription:
    async with SessionLocal() as db:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return sub


@pytest.mark.asyncio
async def test_issue_requires_authentication(client, cloud) -> None:
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies={"csrf_token": "x"},
        headers={"X-CSRF-Token": "x"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_issue_requires_an_active_subscription(client, signed_in_user, cloud) -> None:
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "subscription_required"
    assert cloud.create_calls == []


@pytest.mark.asyncio
async def test_issue_returns_the_plaintext_token_once(client, signed_in_user, cloud) -> None:
    sub = await _active_subscription(signed_in_user["user"].id)
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("sfc_")
    assert body["cloud_tenant_id"].startswith("t_")

    parsed = parse_account_token(body["token"])
    assert parsed is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert verify_account_secret(parsed.secret, PEPPER, tenant.account_token_hash) is True


@pytest.mark.asyncio
async def test_the_token_is_never_returned_again(client, signed_in_user, cloud) -> None:
    await _active_subscription(signed_in_user["user"].id)
    issued = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    token = issued.json()["token"]

    me = await client.get("/api/v1/tenants/me", cookies=signed_in_user["cookies"])
    assert me.status_code == 200
    assert token not in me.text
    assert "token" not in me.json()
    assert me.json()["account_token_issued_at"] is not None


@pytest.mark.asyncio
async def test_issuing_again_rotates_the_token(client, signed_in_user, cloud) -> None:
    sub = await _active_subscription(signed_in_user["user"].id)
    first = (
        await client.post(
            "/api/v1/tenants/account-token",
            cookies=signed_in_user["cookies"],
            headers={"X-CSRF-Token": signed_in_user["csrf"]},
        )
    ).json()
    second = (
        await client.post(
            "/api/v1/tenants/account-token",
            cookies=signed_in_user["cookies"],
            headers={"X-CSRF-Token": signed_in_user["csrf"]},
        )
    ).json()

    assert first["token"] != second["token"]
    assert first["cloud_tenant_id"] == second["cloud_tenant_id"]
    assert len(cloud.tenants) == 1

    old = parse_account_token(first["token"])
    assert old is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert verify_account_secret(old.secret, PEPPER, tenant.account_token_hash) is False


@pytest.mark.asyncio
async def test_tenants_me_returns_404_before_a_tenant_exists(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/tenants/me", cookies=signed_in_user["cookies"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_tenant"
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/tenants
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/tenants/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/tenants/test_routes.py -q`
Expected: FAIL with "assert 404 == 401" (no `/api/v1/tenants/account-token` route exists)

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/tenants/routes.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..cloud.deps import get_cloud
from ..core.config import settings
from ..core.rate_limit import limiter
from ..db.session import get_db
from ..models.billing import Subscription
from ..models.tenant import Tenant
from ..models.user import User
from .service import issue_account_token

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

_ENTITLED_STATUSES = frozenset({"active", "trialing", "past_due"})


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/me")
async def get_tenant(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Tenant metadata only. The account token is NEVER returned here."""
    tenant = await db.scalar(select(Tenant).where(Tenant.user_id == user.id))
    if tenant is None:
        raise _err("no_tenant", "No hosted tenant exists for this account yet.", 404)
    return {
        "cloud_tenant_id": tenant.cloud_tenant_id,
        "tenant_lookup_id": tenant.tenant_lookup_id,
        "account_token_issued_at": (
            tenant.account_token_issued_at.isoformat()
            if tenant.account_token_issued_at
            else None
        ),
    }


@router.post("/account-token", status_code=201)
@limiter.limit("5/hour")
async def issue_token(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mint a new account token and return the plaintext EXACTLY ONCE.

    Calling this again is rotation: the previous token stops working immediately.
    Only the scrypt hash is stored; the plaintext is never logged or re-readable.
    """
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None or subscription.status not in _ENTITLED_STATUSES:
        raise _err(
            "subscription_required",
            "An active subscription is required to issue an account token.",
            402,
        )
    issued = await issue_account_token(
        db, get_cloud(), subscription=subscription, pepper=settings.ACCOUNT_TOKEN_PEPPER
    )
    await db.commit()
    return {
        "token": issued.token,
        "cloud_tenant_id": issued.cloud_tenant_id,
        "issued_at": issued.issued_at.isoformat(),
    }
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — extend the deferred import block:

```python
from app.tenants.routes import router as tenants_router  # noqa: E402

app.include_router(tenants_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/tenants/test_routes.py -q`
Expected: PASS — "6 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/tenants/routes.py backend/src/app/main.py backend/tests/integration/tenants
git commit -m "feat: issue and rotate sfc_ account tokens, shown exactly once"
```

---

### Task 26: Install routes and the cloud read proxies

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/installs/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/installs/routes.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/installs/test_routes.py`

**Interfaces:**
- Consumes: `app.auth.deps.verified_user`, `app.cloud.deps.get_cloud`, `app.models.install.Install`, `app.models.tenant.Tenant`, `app.cloud.errors.NotWiredError`.
- Produces: `GET /api/v1/installs -> [{"id","name","created_at","last_seen_at"}]`; `POST /api/v1/installs -> 201 {...}`; `DELETE /api/v1/installs/{id} -> 204`; `GET /api/v1/installs/ingress-urls -> {"ingress_urls": [...]}`; `GET /api/v1/installs/deliveries?limit=N -> {"deliveries": [...]}`. Both proxies return `503 cloud_unavailable` when the transport is not wired.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/installs/test_routes.py`:

```python
import uuid

import pytest

from app.cloud.contracts import DeliveryRecord, IngressUrl
from app.cloud.deps import set_cloud
from app.cloud.http import HttpCloudControlPlane
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _tenant_for(user_id: uuid.UUID, cloud_tenant_id: str = "t_test") -> Tenant:
    async with SessionLocal() as db:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(sub)
        await db.flush()
        tenant = Tenant(
            id=uuid.uuid4(),
            user_id=user_id,
            subscription_id=sub.id,
            cloud_tenant_id=cloud_tenant_id,
            tenant_lookup_id=uuid.uuid4().hex[:18],
            account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
            account_token_hash_algo="scrypt",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant


@pytest.mark.asyncio
async def test_installs_start_empty(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_list_and_delete_an_install(client, signed_in_user, cloud) -> None:
    created = await client.post(
        "/api/v1/installs",
        json={"name": "Work laptop"},
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert created.status_code == 201
    install_id = created.json()["id"]
    assert created.json()["name"] == "Work laptop"

    listed = await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])
    assert [i["name"] for i in listed.json()] == ["Work laptop"]

    deleted = await client.delete(
        f"/api/v1/installs/{install_id}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])).json() == []


@pytest.mark.asyncio
async def test_deleting_someone_elses_install_is_404(client, signed_in_user, cloud) -> None:
    r = await client.delete(
        f"/api/v1/installs/{uuid.uuid4()}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "install_not_found"


@pytest.mark.asyncio
async def test_ingress_urls_require_a_tenant(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_tenant"


@pytest.mark.asyncio
async def test_ingress_urls_proxy_the_cloud_control_plane(client, signed_in_user, cloud) -> None:
    await _tenant_for(signed_in_user["user"].id, "t_proxy")
    cloud.seed_ingress_url(
        "t_proxy",
        IngressUrl(
            id="ig_1", integration="stripe",
            url="https://wh.example.invalid/wh/ig_1", created_at="2026-07-21T10:00:00.000Z",
        ),
    )
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == {
        "ingress_urls": [
            {
                "id": "ig_1",
                "integration": "stripe",
                "url": "https://wh.example.invalid/wh/ig_1",
                "created_at": "2026-07-21T10:00:00.000Z",
            }
        ]
    }


@pytest.mark.asyncio
async def test_deliveries_proxy_the_cloud_control_plane(client, signed_in_user, cloud) -> None:
    await _tenant_for(signed_in_user["user"].id, "t_deliver")
    cloud.seed_delivery(
        "t_deliver",
        DeliveryRecord(
            delivery_id="dl_1", ingress_id="ig_1", integration="stripe",
            received_at="2026-07-21T10:00:01.000Z", status="published",
        ),
    )
    r = await client.get(
        "/api/v1/installs/deliveries?limit=10", cookies=signed_in_user["cookies"]
    )
    assert r.status_code == 200
    assert r.json()["deliveries"][0]["delivery_id"] == "dl_1"


@pytest.mark.asyncio
async def test_proxies_return_503_when_the_cloud_transport_is_not_wired(
    client, signed_in_user
) -> None:
    """The deferred HTTP transport must surface as a legible 503, not a 500."""
    set_cloud(HttpCloudControlPlane("https://cloud.example.invalid", "k"))
    await _tenant_for(signed_in_user["user"].id, "t_unwired")
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "cloud_unavailable"
    set_cloud(InMemoryCloudControlPlane())
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/installs
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/installs/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/installs/test_routes.py -q`
Expected: FAIL with "assert 404 == 200" (no `/api/v1/installs` route exists)

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/installs/routes.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..cloud.deps import get_cloud
from ..cloud.errors import CloudError, NotWiredError
from ..db.session import get_db
from ..models.install import Install
from ..models.tenant import Tenant
from ..models.user import User

router = APIRouter(prefix="/api/v1/installs", tags=["installs"])
log = structlog.get_logger(__name__)


class CreateInstallRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _install_out(i: Install) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "name": i.name,
        "created_at": i.created_at.isoformat(),
        "last_seen_at": i.last_seen_at.isoformat() if i.last_seen_at else None,
    }


async def _require_tenant(db: AsyncSession, user: User) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.user_id == user.id))
    if tenant is None:
        raise _err("no_tenant", "No hosted tenant exists for this account yet.", 404)
    return tenant


@router.get("")
async def list_installs(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Install).where(Install.user_id == user.id).order_by(Install.created_at)
        )
    ).scalars().all()
    return [_install_out(i) for i in rows]


@router.post("", status_code=201)
async def create_install(
    body: CreateInstallRequest,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    install = Install(id=uuid.uuid4(), user_id=user.id, name=body.name)
    db.add(install)
    await db.commit()
    await db.refresh(install)
    return _install_out(install)


@router.delete("/{install_id}", status_code=204)
async def delete_install(
    install_id: uuid.UUID,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    install = await db.scalar(
        select(Install).where(Install.id == install_id, Install.user_id == user.id)
    )
    if install is None:
        raise _err("install_not_found", "Install not found.", 404)
    await db.delete(install)
    await db.commit()


@router.get("/ingress-urls")
async def list_ingress_urls(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    tenant = await _require_tenant(db, user)
    try:
        urls = await get_cloud().list_ingress_urls(tenant.cloud_tenant_id)
    except NotWiredError as exc:
        log.warning("cloud_not_wired", transport=exc.transport)
        raise _err(
            "cloud_unavailable",
            "Hosted ingress is not available yet — the relay is not connected.",
            503,
        ) from None
    except CloudError as exc:
        log.warning("cloud_error", code=exc.code)
        raise _err("cloud_unavailable", "The relay could not be reached — retry shortly.", 503) from None
    return {"ingress_urls": [u.to_api() for u in urls]}


@router.get("/deliveries")
async def list_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant = await _require_tenant(db, user)
    try:
        deliveries = await get_cloud().get_delivery_history(tenant.cloud_tenant_id, limit=limit)
    except NotWiredError as exc:
        log.warning("cloud_not_wired", transport=exc.transport)
        raise _err(
            "cloud_unavailable",
            "Delivery history is not available yet — the relay is not connected.",
            503,
        ) from None
    except CloudError as exc:
        log.warning("cloud_error", code=exc.code)
        raise _err("cloud_unavailable", "The relay could not be reached — retry shortly.", 503) from None
    return {"deliveries": [d.to_api() for d in deliveries]}
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — extend the deferred import block:

```python
from app.installs.routes import router as installs_router  # noqa: E402

app.include_router(installs_router)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/installs
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/installs/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/ -q`
Expected: PASS — the full backend suite passes with "0 failed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/installs backend/src/app/main.py backend/tests/integration/installs
git commit -m "feat: add install management and cloud ingress/delivery read proxies"
```

---

### Task 27: Brand layer and frontend scaffold

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/packages/ui/package.json`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/packages/ui/tsconfig.json`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/packages/ui/src/**` (copied)
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/package.json`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/tsconfig.json`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/next.config.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/postcss.config.mjs`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/vitest.config.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/vitest.setup.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/globals.css` (copied)
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/fonts/ClashDisplay-Variable.woff2` (copied)
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/__tests__/brand.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: workspace package `@saiife/ui` exporting `.`, `./tokens.css`, `./tailwind-preset`; workspace package `frontend` with the `@/*` alias, `pnpm vitest run` and `pnpm build` scripts.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/__tests__/brand.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// Vitest runs this as ESM, so `__dirname` does not exist.
const HERE = dirname(fileURLToPath(import.meta.url));
const UI_SRC = join(HERE, "../../../../packages/ui/src");

describe("brand layer", () => {
  it("ships the brand tokens copied from saiife.com-old", () => {
    const tokens = readFileSync(join(UI_SRC, "tokens.css"), "utf8");
    expect(tokens).toContain("--brand-from");
    expect(tokens).toContain("--brand-to");
    expect(tokens).toContain("--border-glow");
  });

  it("ships the brand primitives", () => {
    for (const file of [
      "GradientButton.tsx",
      "Eyebrow.tsx",
      "RingIconBadge.tsx",
      "SpotlightCard.tsx",
      "tailwind.preset.ts",
    ]) {
      expect(() => readFileSync(join(UI_SRC, file), "utf8")).not.toThrow();
    }
  });

  it("exports the brand primitives from the package entry point", () => {
    const index = readFileSync(join(UI_SRC, "index.ts"), "utf8");
    for (const name of ["GradientButton", "Eyebrow", "RingIconBadge", "SpotlightCard"]) {
      expect(index).toContain(name);
    }
  });

  it("wires the ClashDisplay face into globals.css via --font-display", () => {
    const globals = readFileSync(join(HERE, "../../app/globals.css"), "utf8");
    expect(globals).toContain("--font-display");
    expect(globals).toContain("@saiife/ui/tokens.css");
    expect(globals).toContain('@source "../../../packages/ui/src"');
  });

  it("no longer reaches for @base-ui — the dead root-level duplicates are gone", () => {
    const index = readFileSync(join(UI_SRC, "index.ts"), "utf8");
    expect(index).not.toContain("LockedFeature");
    for (const dead of ["Button.tsx", "Badge.tsx", "Card.tsx", "Input.tsx", "Label.tsx"]) {
      expect(() => readFileSync(join(UI_SRC, dead), "utf8")).toThrow();
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/lib/__tests__/brand.test.ts`
Expected: FAIL with "Cannot find module 'vitest'" (no frontend package installed yet)

- [ ] **Step 3: Write minimal implementation**

Copy the brand layer and shadcn set verbatim from saiife.com-old, then drop the components hub does not use:

```bash
SRC=/home/jonasrobinson/projects/saiife/saiife.com-old
DST=/home/jonasrobinson/projects/saiife/saiife-hub
mkdir -p "$DST/packages/ui/src" "$DST/frontend/src/app/fonts" "$DST/frontend/src/lib/__tests__"
cp -R "$SRC/packages/ui/src/." "$DST/packages/ui/src/"
cp "$SRC/app/src/app/globals.css" "$DST/frontend/src/app/globals.css"
cp "$SRC/app/src/app/fonts/ClashDisplay-Variable.woff2" "$DST/frontend/src/app/fonts/"
cp "$SRC/app/src/app/icon.svg" "$DST/frontend/src/app/icon.svg"

# Drop the dead root-level duplicates. index.ts exports Button/Badge/Card/Input/
# Label from ./components/ui/*, so these five files are unreachable — and they are
# the ONLY things in the package that import @base-ui/react. Deleting them removes
# a dependency instead of adding one.
rm -f "$DST/packages/ui/src/Button.tsx" \
      "$DST/packages/ui/src/Badge.tsx" \
      "$DST/packages/ui/src/Card.tsx" \
      "$DST/packages/ui/src/Input.tsx" \
      "$DST/packages/ui/src/Label.tsx"

# LockedFeature is scan/PR product surface — hub has no use for it.
rm -f "$DST/packages/ui/src/LockedFeature.tsx"
sed -i '/LockedFeature/d' "$DST/packages/ui/src/index.ts"

# Prove nothing left behind reaches for @base-ui.
! grep -rq "@base-ui" "$DST/packages/ui/src"
```

`globals.css` needs no edit: it already contains `@source "../../../packages/ui/src";`,
and `frontend/src/app/` sits at the same depth below the repo root as the old
`app/src/app/`, so the relative path still resolves to `packages/ui/src`.

`/home/jonasrobinson/projects/saiife/saiife-hub/packages/ui/package.json`:

```json
{
  "name": "@saiife/ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts",
    "./tokens.css": "./src/tokens.css",
    "./tailwind-preset": "./src/tailwind.preset.ts"
  },
  "scripts": {
    "build": "tsc --noEmit",
    "lint": "tsc --noEmit"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwindcss": "^4"
  },
  "dependencies": {
    "@radix-ui/react-avatar": "^1.1.11",
    "@radix-ui/react-dialog": "^1.1.15",
    "@radix-ui/react-dropdown-menu": "^2.1.16",
    "@radix-ui/react-separator": "^1.1.8",
    "@radix-ui/react-slot": "^1.2.4",
    "@radix-ui/react-tabs": "^1.1.13",
    "@radix-ui/react-tooltip": "^1.2.8",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^1.14.0",
    "next-themes": "^0.4.6",
    "radix-ui": "^1.4.3",
    "sonner": "^2.0.7",
    "tailwind-merge": "^3.5.0"
  },
  "devDependencies": {
    "@types/react": "^19",
    "tailwindcss": "^4",
    "tailwindcss-animate": "^1.0.7",
    "typescript": "^5"
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/packages/ui/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "jsx": "react-jsx",
    "module": "esnext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*.ts", "src/**/*.tsx"]
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/package.json`:

```json
{
  "name": "frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3001",
    "build": "next build",
    "start": "next start -p 3001",
    "lint": "next lint",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@saiife/ui": "workspace:*",
    "@simplewebauthn/browser": "^11.0.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^1.14.0",
    "next": "16.2.6",
    "next-themes": "^0.4.6",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "sonner": "^2.0.7",
    "tailwind-merge": "^3.5.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.59.1",
    "@tailwindcss/postcss": "^4",
    "@testing-library/jest-dom": "^6.9.1",
    "@testing-library/react": "^16.3.2",
    "@testing-library/user-event": "^14.5.2",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "@vitejs/plugin-react": "^6.0.1",
    "eslint": "^9",
    "eslint-config-next": "16.2.6",
    "jsdom": "^29.1.1",
    "tailwindcss": "^4",
    "typescript": "^5",
    "vitest": "^4.1.5"
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "types": ["node", "vitest/globals", "@testing-library/jest-dom"],
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// The API origin the browser may call. NEXT_PUBLIC_* is inlined at BUILD time, so
// each environment builds its own image (see cloudbuild.yaml).
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

// Next emits inline <script> for the RSC payload and the next-themes FOUC script,
// so 'unsafe-inline' is required for hydration. 'unsafe-eval' is dev-only (HMR).
const csp = [
  "default-src 'self'",
  isDev ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  `connect-src 'self' ${apiUrl}` + (isDev ? " ws: wss:" : ""),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  typedRoutes: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default config;
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/postcss.config.mjs`:

```js
export default { plugins: { "@tailwindcss/postcss": {} } };
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/vitest.config.ts`:

```ts
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/vitest.setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Install the workspace:

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub && pnpm install
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/lib/__tests__/brand.test.ts`
Expected: PASS — "5 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add packages frontend pnpm-lock.yaml
git commit -m "feat: copy the brand layer and scaffold the Next.js frontend"
```

---

### Task 28: Frontend API client, CSRF, auth context, passkey helpers

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/csrf.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/auth-context.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/theme.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/passkey.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/billing.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/tenants.ts`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/installs.ts`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: the backend routes from Tasks 9-26.
- Produces: `api<T>(path, init?) -> Promise<T>`, `ApiException(status, code, message, details?)`, `readCsrfToken()`, `AuthProvider`, `useAuth()`, `Me`, `AppThemeProvider`, `registerPasskey(name)`, `loginWithPasskey()`, `getSubscription()`, `createCheckoutSession()`, `createPortalSession()`, `issueAccountToken()`, `getTenant()`, `listInstalls()`, `createInstall(name)`, `deleteInstall(id)`, `listIngressUrls()`, `listDeliveries(limit?)`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/__tests__/api.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiException, api } from "@/lib/api";

const API_URL = "https://api.saiife.localhost:8000";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  document.cookie = "csrf_token=tok-123";
});

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api", () => {
  it("sends credentials and the CSRF header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/auth/me");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/v1/auth/me`);
    expect(init.credentials).toBe("include");
    expect(init.headers["X-CSRF-Token"]).toBe("tok-123");
  });

  it("serialises the json option and sets the content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/auth/login", { method: "POST", json: { email: "a@b.co" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ email: "a@b.co" }));
  });

  it("throws ApiException carrying the backend error code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "invalid_credentials", message: "nope" } }, 401),
      ),
    );

    await expect(api("/api/v1/auth/login", { method: "POST" })).rejects.toMatchObject({
      status: 401,
      code: "invalid_credentials",
    });
  });

  it("refreshes once on token_expired then replays the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "token_expired", message: "expired" } }, 401),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ id: "u1" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api<{ id: string }>("/api/v1/auth/me");

    expect(result).toEqual({ id: "u1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_URL}/api/v1/auth/refresh`);
  });

  it("does not retry a 401 that is not a session-expiry code", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error: { code: "invalid_credentials", message: "nope" } }, 401),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/api/v1/auth/me")).rejects.toBeInstanceOf(ApiException);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns undefined for a 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api("/api/v1/installs/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/lib/__tests__/api.test.ts`
Expected: FAIL with "Failed to resolve import \"@/lib/api\""

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/csrf.ts`:

```ts
export function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api.ts`:

```ts
import { readCsrfToken } from "./csrf";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

export type ApiError = { error: { code: string; message: string; details?: unknown } };

export class ApiException extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

let refreshInFlight: Promise<boolean> | null = null;

function csrfHeader(): Record<string, string> {
  const t = readCsrfToken();
  return t ? { "X-CSRF-Token": t } : {};
}

async function refreshOnce(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: csrfHeader(),
    })
      .then((r) => r.ok)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const opts: RequestInit = {
    credentials: "include",
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...csrfHeader(),
      ...((headers as Record<string, string> | undefined) ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : (rest.body as BodyInit | undefined),
  };

  let res = await fetch(`${API_URL}${path}`, opts);
  if (res.status === 401) {
    const body: ApiError | null = await res
      .clone()
      .json()
      .catch(() => null);
    // The access cookie expired (token_expired) or was dropped after its Max-Age
    // (no_session) — the 30-day refresh cookie can still mint a new one.
    const code = body?.error?.code;
    if ((code === "token_expired" || code === "no_session") && (await refreshOnce())) {
      res = await fetch(`${API_URL}${path}`, opts);
    }
  }

  if (!res.ok) {
    const body: ApiError = await res.json().catch(() => ({
      error: { code: "unknown", message: res.statusText },
    }));
    throw new ApiException(res.status, body.error.code, body.error.message, body.error.details);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/auth-context.tsx`:

```tsx
"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiException, api } from "./api";

export type Me = { id: string; email: string; email_verified: boolean };

type Ctx = {
  user: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setUser: (u: Me | null) => void;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      setUser(await api<Me>("/api/v1/auth/me"));
    } catch (e) {
      if (e instanceof ApiException && e.status === 401) setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" });
    setUser(null);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, refresh, setUser, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): Ctx {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/theme.tsx`:

```tsx
"use client";
import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

export function AppThemeProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
      {children}
    </ThemeProvider>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/passkey.ts`:

```ts
import { startAuthentication, startRegistration } from "@simplewebauthn/browser";

import { api } from "./api";

type RegistrationOptions = Parameters<typeof startRegistration>[0]["optionsJSON"];
type AuthenticationOptions = Parameters<typeof startAuthentication>[0]["optionsJSON"];

type StartRegistration = { challenge_id: string; options: RegistrationOptions };
type StartAuthentication = { challenge_id: string; options: AuthenticationOptions };

export async function registerPasskey(name: string): Promise<{ id: string; name: string }> {
  const start = await api<StartRegistration>("/api/v1/auth/passkey/register/start", {
    method: "POST",
  });
  const response = await startRegistration({ optionsJSON: start.options });
  return api("/api/v1/auth/passkey/register/finish", {
    method: "POST",
    json: { challenge_id: start.challenge_id, name, response },
  });
}

export async function loginWithPasskey(): Promise<void> {
  const start = await api<StartAuthentication>("/api/v1/auth/passkey/login/start", {
    method: "POST",
  });
  const response = await startAuthentication({ optionsJSON: start.options });
  await api("/api/v1/auth/passkey/login/finish", {
    method: "POST",
    json: { challenge_id: start.challenge_id, response },
  });
}

export type PasskeySummary = {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
};

export function listPasskeys() {
  return api<PasskeySummary[]>("/api/v1/auth/passkeys");
}

export function renamePasskey(id: string, name: string) {
  return api<{ id: string; name: string }>(`/api/v1/auth/passkeys/${id}`, {
    method: "PATCH",
    json: { name },
  });
}

export function deletePasskey(id: string) {
  return api<void>(`/api/v1/auth/passkeys/${id}`, { method: "DELETE" });
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/billing.ts`:

```ts
import { api } from "@/lib/api";

export type SubscriptionStatus = {
  status: string;
  current_period_end: string | null;
  has_tenant: boolean;
  account_token_issued_at: string | null;
};

export function getSubscription() {
  return api<SubscriptionStatus>("/api/v1/billing/subscription");
}

export function createCheckoutSession() {
  return api<{ url: string }>("/api/v1/billing/checkout-session", { method: "POST" });
}

export function createPortalSession() {
  return api<{ url: string }>("/api/v1/billing/portal-session", { method: "POST" });
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/tenants.ts`:

```ts
import { api } from "@/lib/api";

export type TenantSummary = {
  cloud_tenant_id: string;
  tenant_lookup_id: string;
  account_token_issued_at: string | null;
};

export type IssuedToken = {
  token: string;
  cloud_tenant_id: string;
  issued_at: string;
};

export function getTenant() {
  return api<TenantSummary>("/api/v1/tenants/me");
}

/** Returns the plaintext token EXACTLY ONCE. Never persist it client-side. */
export function issueAccountToken() {
  return api<IssuedToken>("/api/v1/tenants/account-token", { method: "POST" });
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/lib/api/installs.ts`:

```ts
import { api } from "@/lib/api";

export type Install = {
  id: string;
  name: string;
  created_at: string;
  last_seen_at: string | null;
};

export type IngressUrl = {
  id: string;
  integration: string;
  url: string;
  created_at: string;
};

export type Delivery = {
  delivery_id: string;
  ingress_id: string;
  integration: string;
  received_at: string;
  status: string;
};

export function listInstalls() {
  return api<Install[]>("/api/v1/installs");
}

export function createInstall(name: string) {
  return api<Install>("/api/v1/installs", { method: "POST", json: { name } });
}

export function deleteInstall(id: string) {
  return api<void>(`/api/v1/installs/${id}`, { method: "DELETE" });
}

export function listIngressUrls() {
  return api<{ ingress_urls: IngressUrl[] }>("/api/v1/installs/ingress-urls");
}

export function listDeliveries(limit = 50) {
  return api<{ deliveries: Delivery[] }>(`/api/v1/installs/deliveries?limit=${limit}`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/lib/__tests__/api.test.ts`
Expected: PASS — "6 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add frontend/src/lib
git commit -m "feat: add frontend API client, CSRF, auth context and typed endpoint helpers"
```

---

### Task 29: Public pages and the auth form

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/layout.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/layout.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/login/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/signup/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/verify-email/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/oauth-callback/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AuthForm.tsx`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/AuthForm.test.tsx`

**Interfaces:**
- Consumes: `api`, `ApiException`, `useAuth`, `loginWithPasskey`.
- Produces: `AuthForm({ mode }: { mode: "signup" | "login" })`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/AuthForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthForm } from "@/components/AuthForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: push }) }));

const refresh = vi.fn();
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ refresh }) }));

const apiMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: (...args: unknown[]) => apiMock(...args) };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AuthForm", () => {
  it("posts signup and then shows the check-your-inbox panel", async () => {
    apiMock.mockResolvedValue({});
    render(<AuthForm mode="signup" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/v1/auth/signup", {
        method: "POST",
        json: { email: "alice@example.com", password: "correct-horse-battery-staple" },
      });
    });
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
  });

  it("posts login, refreshes the session and navigates to the dashboard", async () => {
    apiMock.mockResolvedValue({});
    render(<AuthForm mode="login" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("renders a friendly message for a known backend error code", async () => {
    const { ApiException } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    apiMock.mockRejectedValue(new ApiException(403, "email_unverified", "nope"));
    render(<AuthForm mode="login" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/verify your email before signing in/i),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/components/__tests__/AuthForm.test.tsx`
Expected: FAIL with "Failed to resolve import \"@/components/AuthForm\""

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AuthForm.tsx`:

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Input } from "@saiife/ui";
import { ApiException, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { loginWithPasskey } from "@/lib/passkey";

type Mode = "signup" | "login";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

const TABS = ["passkey", "google", "password"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = { passkey: "passkey", google: "google", password: "email" };

export function AuthForm({ mode }: { mode: Mode }) {
  const [tab, setTab] = useState<Tab>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [verifyEmailSent, setVerifyEmailSent] = useState(false);
  const router = useRouter();
  const { refresh } = useAuth();

  async function submitPassword(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await api("/api/v1/auth/signup", { method: "POST", json: { email, password } });
        setVerifyEmailSent(true);
      } else {
        await api("/api/v1/auth/login", { method: "POST", json: { email, password } });
        await refresh();
        router.push("/dashboard");
      }
    } catch (e) {
      if (e instanceof ApiException) {
        setError(
          e.code === "email_unverified"
            ? "Verify your email before signing in."
            : e.code === "email_taken"
              ? "An account with this email already exists."
              : e.code === "invalid_credentials"
                ? "Email or password is incorrect."
                : e.message,
        );
      } else {
        setError("Something went wrong — try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function startGoogle() {
    window.location.href = `${API_URL}/api/v1/auth/google/start`;
  }

  async function doPasskey() {
    setError(null);
    setSubmitting(true);
    try {
      await loginWithPasskey();
      await refresh();
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof ApiException ? e.message : "Passkey login was cancelled or failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (verifyEmailSent) {
    return (
      <div className="frame ticks px-6 py-8 text-center">
        <div className="briefing-label mx-auto w-fit">check your inbox</div>
        <p className="mt-4 font-mono text-xs leading-relaxed text-muted-foreground">
          We sent a verification link to <span className="text-foreground/80">{email}</span>. Click
          it to finish signing up.
        </p>
      </div>
    );
  }

  return (
    <div className="frame ticks space-y-5 px-6 py-7">
      <div className="grid grid-cols-3 gap-1.5">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`stamp rounded border py-1.5 text-[10px] uppercase tracking-wide transition-colors ${
              tab === t
                ? "border-foreground/40 text-foreground"
                : "border-border text-muted-foreground hover:border-border/70 hover:text-foreground/70"
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === "password" && (
        <form onSubmit={submitPassword} className="space-y-4">
          <div>
            <label className="briefing-label" htmlFor="email">
              email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-2 h-10 font-mono"
            />
          </div>
          <div>
            <label className="briefing-label" htmlFor="pw">
              password
            </label>
            <Input
              id="pw"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-2 h-10 font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
          >
            <span>{submitting ? "Working…" : mode === "signup" ? "Create account" : "Sign in"}</span>
            <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
          </button>
        </form>
      )}

      {tab === "google" && (
        <button
          type="button"
          onClick={startGoogle}
          className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <span>Continue with Google</span>
          <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
        </button>
      )}

      {tab === "passkey" && (
        <button
          type="button"
          onClick={doPasskey}
          disabled={submitting}
          className="group flex h-11 w-full items-center justify-between rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          <span>
            {submitting
              ? "Working…"
              : mode === "signup"
                ? "Register a passkey"
                : "Sign in with passkey"}
          </span>
          <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
        </button>
      )}

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </div>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/layout.tsx`:

```tsx
import { Geist, Geist_Mono } from "next/font/google";
import localFont from "next/font/local";

import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { AppThemeProvider } from "@/lib/theme";

const display = localFont({
  src: "./fonts/ClashDisplay-Variable.woff2",
  weight: "700",
  display: "swap",
  variable: "--font-display",
});
const sans = Geist({ subsets: ["latin"], variable: "--font-sans-src" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono-src" });

export const metadata = {
  title: "saiife hub",
  description: "Hosted webhook ingress for your saiife install.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen antialiased">
        <AppThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </AppThemeProvider>
      </body>
    </html>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard");
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/layout.tsx`:

```tsx
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return <main className="grid min-h-screen place-items-center p-6">{children}</main>;
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/login/page.tsx`:

```tsx
import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="briefing-in text-center">
        <div className="display text-4xl text-foreground">saiife</div>
        <h1 className="display mt-2 text-xl text-muted-foreground">Sign in</h1>
      </div>
      <div className="briefing-in" style={{ animationDelay: "0.05s" }}>
        <AuthForm mode="login" />
      </div>
      <p
        className="briefing-in text-center font-mono text-[11px] text-muted-foreground"
        style={{ animationDelay: "0.1s" }}
      >
        no account yet?{" "}
        <Link
          href="/signup"
          className="text-foreground/70 underline underline-offset-2 transition-colors hover:text-foreground"
        >
          create one
        </Link>
      </p>
    </div>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/signup/page.tsx`:

```tsx
import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function SignupPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="briefing-in text-center">
        <div className="display text-4xl text-foreground">saiife</div>
        <h1 className="display mt-2 text-xl text-muted-foreground">Create your account</h1>
      </div>
      <div className="briefing-in" style={{ animationDelay: "0.05s" }}>
        <AuthForm mode="signup" />
      </div>
      <p
        className="briefing-in text-center font-mono text-[11px] text-muted-foreground"
        style={{ animationDelay: "0.1s" }}
      >
        already have an account?{" "}
        <Link
          href="/login"
          className="text-foreground/70 underline underline-offset-2 transition-colors hover:text-foreground"
        >
          sign in
        </Link>
      </p>
    </div>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/verify-email/page.tsx`:

```tsx
"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ApiException, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function VerifyEmailInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setError("This verification link is missing its token.");
      return;
    }
    api("/api/v1/auth/verify-email", { method: "POST", json: { token } })
      .then(async () => {
        await refresh();
        router.replace("/dashboard");
      })
      .catch((e) =>
        setError(e instanceof ApiException ? e.message : "Verification failed."),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
        {error}
      </p>
    );
  }
  return <p className="stamp text-xs text-muted-foreground">verifying…</p>;
}

export default function VerifyEmailPage() {
  return (
    <div className="frame ticks w-full max-w-sm px-6 py-10 text-center">
      <div className="briefing-label mx-auto w-fit">email verification</div>
      <div className="mt-6 flex justify-center">
        <Suspense fallback={<p className="stamp text-xs text-muted-foreground">verifying…</p>}>
          <VerifyEmailInner />
        </Suspense>
      </div>
    </div>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(public)/oauth-callback/page.tsx`:

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export default function OAuthCallback() {
  const router = useRouter();
  const { refresh } = useAuth();
  useEffect(() => {
    void refresh().then(() => router.replace("/dashboard"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="frame ticks w-full max-w-sm px-6 py-10 text-center">
      <div className="briefing-label mx-auto w-fit">oauth</div>
      <p className="stamp mt-6 text-xs text-muted-foreground">finishing sign-in…</p>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/components/__tests__/AuthForm.test.tsx`
Expected: PASS — "3 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add frontend/src/app frontend/src/components
git commit -m "feat: add public auth pages and the password/google/passkey auth form"
```

---

### Task 30: Authed shell, security settings and passkey management

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/layout.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/settings/security/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AccountShell.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/PasskeyList.tsx`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/PasskeyList.test.tsx`

**Interfaces:**
- Consumes: `useAuth`, `listPasskeys`, `registerPasskey`, `renamePasskey`, `deletePasskey`.
- Produces: `AccountShell({ email, children })`, `PasskeyList()`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/PasskeyList.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PasskeyList } from "@/components/PasskeyList";

const listPasskeys = vi.fn();
const registerPasskey = vi.fn();
const deletePasskey = vi.fn();

vi.mock("@/lib/passkey", () => ({
  listPasskeys: () => listPasskeys(),
  registerPasskey: (name: string) => registerPasskey(name),
  deletePasskey: (id: string) => deletePasskey(id),
  renamePasskey: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("PasskeyList", () => {
  it("renders an empty state when there are no passkeys", async () => {
    listPasskeys.mockResolvedValue([]);
    render(<PasskeyList />);
    expect(await screen.findByText(/no passkeys registered/i)).toBeInTheDocument();
  });

  it("lists the registered passkeys", async () => {
    listPasskeys.mockResolvedValue([
      { id: "p1", name: "Work laptop", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
    ]);
    render(<PasskeyList />);
    expect(await screen.findByText("Work laptop")).toBeInTheDocument();
  });

  it("registers a new passkey and reloads the list", async () => {
    listPasskeys.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { id: "p1", name: "Phone", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
    ]);
    registerPasskey.mockResolvedValue({ id: "p1", name: "Phone" });
    render(<PasskeyList />);

    await screen.findByText(/no passkeys registered/i);
    await userEvent.type(await screen.findByLabelText(/passkey name/i), "Phone");
    await userEvent.click(screen.getByRole("button", { name: /add passkey/i }));

    await waitFor(() => expect(registerPasskey).toHaveBeenCalledWith("Phone"));
    expect(await screen.findByText("Phone")).toBeInTheDocument();
  });

  it("deletes a passkey", async () => {
    listPasskeys
      .mockResolvedValueOnce([
        { id: "p1", name: "Work laptop", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
      ])
      .mockResolvedValueOnce([]);
    deletePasskey.mockResolvedValue(undefined);
    render(<PasskeyList />);

    await userEvent.click(await screen.findByRole("button", { name: /remove work laptop/i }));
    await waitFor(() => expect(deletePasskey).toHaveBeenCalledWith("p1"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/components/__tests__/PasskeyList.test.tsx`
Expected: FAIL with "Failed to resolve import \"@/components/PasskeyList\""

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/PasskeyList.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@saiife/ui";
import {
  deletePasskey,
  listPasskeys,
  registerPasskey,
  type PasskeySummary,
} from "@/lib/passkey";

export function PasskeyList() {
  const [passkeys, setPasskeys] = useState<PasskeySummary[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setPasskeys(await listPasskeys());
    } catch {
      setError("Could not load your passkeys.");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function add() {
    setError(null);
    setBusy(true);
    try {
      await registerPasskey(name || "Unnamed passkey");
      setName("");
      await reload();
    } catch {
      setError("Passkey registration was cancelled or failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    setBusy(true);
    try {
      await deletePasskey(id);
      await reload();
    } catch {
      setError("Could not remove that passkey.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-5 px-6 py-6">
      <div className="briefing-label">passkeys</div>

      {passkeys === null && <p className="stamp text-xs text-muted-foreground">loading…</p>}

      {passkeys !== null && passkeys.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">
          No passkeys registered yet. Add one to sign in without a password.
        </p>
      )}

      {passkeys !== null && passkeys.length > 0 && (
        <ul className="divide-y divide-border">
          {passkeys.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-foreground">{p.name}</div>
                <div className="stamp text-[11px] text-muted-foreground">
                  added {new Date(p.created_at).toLocaleDateString()}
                  {p.last_used_at
                    ? ` · last used ${new Date(p.last_used_at).toLocaleDateString()}`
                    : " · never used"}
                </div>
              </div>
              <button
                type="button"
                aria-label={`Remove ${p.name}`}
                disabled={busy}
                onClick={() => void remove(p.id)}
                className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground transition-colors hover:border-rose-500/60 hover:text-rose-400 disabled:opacity-50"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="briefing-label" htmlFor="pk-name">
            passkey name
          </label>
          <Input
            id="pk-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Work laptop"
            className="mt-2 h-10 font-mono"
          />
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void add()}
          className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          Add passkey
        </button>
      </div>

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AccountShell.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import type { ReactNode } from "react";

import {
  Avatar,
  AvatarFallback,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@saiife/ui";
import { useAuth } from "@/lib/auth-context";

/** Slim console chrome: brand on the left, account menu on the right. */
export function AccountShell({ email, children }: { email: string; children: ReactNode }) {
  const { resolvedTheme, setTheme } = useTheme();
  const router = useRouter();
  const { logout } = useAuth();
  const initials = email.slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-11 items-center justify-between border-b border-border px-4 sm:px-6">
        <div className="flex items-center gap-5">
          <span className="display text-[15px] text-foreground">saiife</span>
          <nav className="flex items-center gap-4">
            <Link href="/dashboard" className="stamp text-xs text-muted-foreground hover:text-foreground">
              dashboard
            </Link>
            <Link href="/billing" className="stamp text-xs text-muted-foreground hover:text-foreground">
              billing
            </Link>
            <Link
              href="/settings/security"
              className="stamp text-xs text-muted-foreground hover:text-foreground"
            >
              security
            </Link>
          </nav>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 items-center gap-2 rounded-sm border border-border px-2 py-1 transition-colors hover:bg-accent/30"
              aria-label="User menu"
            >
              <Avatar className="h-5 w-5 shrink-0 rounded-sm">
                <AvatarFallback className="rounded-sm bg-card font-mono text-[9px] text-muted-foreground">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <span className="stamp hidden max-w-[160px] truncate text-xs text-muted-foreground sm:inline">
                {email}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="bottom" align="end" className="w-56">
            <DropdownMenuLabel className="stamp text-xs text-muted-foreground">
              {email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
              {resolvedTheme === "dark" ? "Switch to light" : "Switch to dark"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={async () => {
                try {
                  await logout();
                } catch {
                  /* the cookies are cleared server-side either way */
                }
                router.push("/login");
              }}
            >
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <main className="flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <div className="mx-auto min-w-0 max-w-3xl">{children}</div>
      </main>
    </div>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/layout.tsx`:

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Toaster, TooltipProvider } from "@saiife/ui";
import { useAuth } from "@/lib/auth-context";

/** Auth gate plus global providers. Page chrome is rendered by AccountShell. */
export default function AuthedLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading]);

  if (loading || !user) return null;

  return (
    <TooltipProvider delayDuration={200}>
      {children}
      <Toaster richColors position="bottom-right" />
    </TooltipProvider>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/settings/security/page.tsx`:

```tsx
"use client";
import { AccountShell } from "@/components/AccountShell";
import { PasskeyList } from "@/components/PasskeyList";
import { useAuth } from "@/lib/auth-context";

export default function SecuritySettings() {
  const { user } = useAuth();
  return (
    <AccountShell email={user?.email ?? ""}>
      <div className="briefing-in mb-8">
        <div className="briefing-label">account · security</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Security</h1>
      </div>
      <PasskeyList />
    </AccountShell>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/components/__tests__/PasskeyList.test.tsx`
Expected: PASS — "4 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add frontend/src/app frontend/src/components
git commit -m "feat: add the authed shell, security settings page and passkey management"
```

---

### Task 31: Dashboard and billing pages

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/SubscriptionCard.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AccountTokenCard.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/InstallsCard.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/IngressUrlsCard.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/DeliveryHistoryCard.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/dashboard/page.tsx`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/billing/page.tsx`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/AccountTokenCard.test.tsx`

**Interfaces:**
- Consumes: `getSubscription`, `createCheckoutSession`, `createPortalSession`, `issueAccountToken`, `listInstalls`, `createInstall`, `deleteInstall`, `listIngressUrls`, `listDeliveries`.
- Produces: `SubscriptionCard({ status, onSubscribe, onManage })`, `AccountTokenCard({ entitled, issuedAt, onIssued })`, `InstallsCard()`, `IngressUrlsCard()`, `DeliveryHistoryCard()`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/__tests__/AccountTokenCard.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountTokenCard } from "@/components/AccountTokenCard";

const issueAccountToken = vi.fn();
vi.mock("@/lib/api/tenants", () => ({
  issueAccountToken: () => issueAccountToken(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("AccountTokenCard", () => {
  it("disables issuance without an active subscription", () => {
    render(<AccountTokenCard entitled={false} issuedAt={null} onIssued={vi.fn()} />);
    expect(screen.getByRole("button", { name: /issue account token/i })).toBeDisabled();
    expect(screen.getByText(/an active subscription is required/i)).toBeInTheDocument();
  });

  it("shows the plaintext token exactly once after issuing", async () => {
    issueAccountToken.mockResolvedValue({
      token: "sfc_0123456789abcdef01_secretsecretsecret",
      cloud_tenant_id: "t_abc",
      issued_at: "2026-07-21T10:00:00+00:00",
    });
    const onIssued = vi.fn();
    render(<AccountTokenCard entitled issuedAt={null} onIssued={onIssued} />);

    await userEvent.click(screen.getByRole("button", { name: /issue account token/i }));

    expect(
      await screen.findByText("sfc_0123456789abcdef01_secretsecretsecret"),
    ).toBeInTheDocument();
    expect(screen.getByText(/shown once/i)).toBeInTheDocument();
    await waitFor(() => expect(onIssued).toHaveBeenCalled());
  });

  it("hides the token again when dismissed", async () => {
    issueAccountToken.mockResolvedValue({
      token: "sfc_0123456789abcdef01_secretsecretsecret",
      cloud_tenant_id: "t_abc",
      issued_at: "2026-07-21T10:00:00+00:00",
    });
    render(<AccountTokenCard entitled issuedAt={null} onIssued={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /issue account token/i }));
    await screen.findByText("sfc_0123456789abcdef01_secretsecretsecret");
    await userEvent.click(screen.getByRole("button", { name: /i saved it/i }));

    expect(
      screen.queryByText("sfc_0123456789abcdef01_secretsecretsecret"),
    ).not.toBeInTheDocument();
  });

  it("labels the action as rotation once a token has been issued before", () => {
    render(
      <AccountTokenCard entitled issuedAt="2026-07-20T10:00:00+00:00" onIssued={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /rotate account token/i })).toBeEnabled();
    expect(screen.getByText(/rotating invalidates/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run src/components/__tests__/AccountTokenCard.test.tsx`
Expected: FAIL with "Failed to resolve import \"@/components/AccountTokenCard\""

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/AccountTokenCard.tsx`:

```tsx
"use client";
import { useState } from "react";

import { issueAccountToken } from "@/lib/api/tenants";

export function AccountTokenCard({
  entitled,
  issuedAt,
  onIssued,
}: {
  entitled: boolean;
  issuedAt: string | null;
  onIssued: () => void;
}) {
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = issuedAt ? "Rotate account token" : "Issue account token";

  async function issue() {
    setError(null);
    setBusy(true);
    try {
      const issued = await issueAccountToken();
      setToken(issued.token);
      onIssued();
    } catch {
      setError("Could not issue a token — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">account token</div>

      {/* Deliberately avoids the phrase "shown once" — that string belongs to the
          reveal box below, so a test can assert on it unambiguously. */}
      <p className="font-mono text-xs leading-relaxed text-muted-foreground">
        Paste this into the saiife desktop app to connect it to hosted ingress. The secret is{" "}
        <span className="text-foreground/80">revealed a single time</span> and never stored — we
        keep only a hash.
      </p>

      {!entitled && (
        <p className="font-mono text-[11px] text-muted-foreground">
          An active subscription is required to issue an account token.
        </p>
      )}

      {issuedAt && (
        <p className="stamp text-[11px] text-muted-foreground">
          last issued {new Date(issuedAt).toLocaleString()} · rotating invalidates the previous
          token immediately
        </p>
      )}

      {token && (
        <div className="space-y-3 rounded-md border border-[var(--border-glow)] bg-card/40 p-4">
          <div className="briefing-label">shown once — copy it now</div>
          <code className="block break-all font-mono text-xs text-foreground">{token}</code>
          <button
            type="button"
            onClick={() => setToken(null)}
            className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:text-foreground"
          >
            I saved it
          </button>
        </div>
      )}

      <button
        type="button"
        disabled={!entitled || busy}
        onClick={() => void issue()}
        className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? "Working…" : label}
      </button>

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/SubscriptionCard.tsx`:

```tsx
"use client";
import type { SubscriptionStatus } from "@/lib/api/billing";

const COPY: Record<string, string> = {
  none: "You do not have a subscription yet.",
  incomplete: "Your checkout has not completed yet.",
  active: "Your subscription is active.",
  past_due: "Payment failed — update your card to keep hosted ingress running.",
  canceled: "Your subscription has been cancelled and your tenant was removed.",
};

export function SubscriptionCard({
  status,
  onSubscribe,
  onManage,
}: {
  status: SubscriptionStatus | null;
  onSubscribe: () => void;
  onManage: () => void;
}) {
  const state = status?.status ?? "none";
  const hasCustomer = state !== "none";

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">subscription</div>
      <p className="font-mono text-xs text-muted-foreground">{COPY[state] ?? state}</p>
      {status?.current_period_end && (
        <p className="stamp text-[11px] text-muted-foreground">
          renews {new Date(status.current_period_end).toLocaleDateString()}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSubscribe}
          className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          {state === "active" ? "Change plan" : "Subscribe"}
        </button>
        {hasCustomer && (
          <button
            type="button"
            onClick={onManage}
            className="h-10 rounded-md border border-border px-4 text-sm text-foreground transition-colors hover:bg-accent/30"
          >
            Manage billing
          </button>
        )}
      </div>
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/InstallsCard.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@saiife/ui";
import { createInstall, deleteInstall, listInstalls, type Install } from "@/lib/api/installs";

export function InstallsCard() {
  const [installs, setInstalls] = useState<Install[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setInstalls(await listInstalls());
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createInstall(name.trim());
      setName("");
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await deleteInstall(id);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">connected installs</div>

      {installs !== null && installs.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">No installs linked yet.</p>
      )}

      {installs !== null && installs.length > 0 && (
        <ul className="divide-y divide-border">
          {installs.map((i) => (
            <li key={i.id} className="flex items-center justify-between py-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-foreground">{i.name}</div>
                <div className="stamp text-[11px] text-muted-foreground">
                  linked {new Date(i.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                aria-label={`Remove ${i.name}`}
                disabled={busy}
                onClick={() => void remove(i.id)}
                className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:border-rose-500/60 hover:text-rose-400 disabled:opacity-50"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="briefing-label" htmlFor="install-name">
            install name
          </label>
          <Input
            id="install-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Work laptop"
            className="mt-2 h-10 font-mono"
          />
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void add()}
          className="h-10 rounded-md border border-border px-4 text-sm text-foreground transition-colors hover:bg-accent/30 disabled:opacity-50"
        >
          Link install
        </button>
      </div>
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/IngressUrlsCard.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";

import { ApiException } from "@/lib/api";
import { listIngressUrls, type IngressUrl } from "@/lib/api/installs";

export function IngressUrlsCard() {
  const [urls, setUrls] = useState<IngressUrl[]>([]);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    listIngressUrls()
      .then((r) => setUrls(r.ingress_urls))
      .catch((e) => {
        if (e instanceof ApiException && e.code === "cloud_unavailable") {
          setNote("Hosted ingress is not connected yet.");
        } else if (e instanceof ApiException && e.code === "no_tenant") {
          setNote("Subscribe to get your ingress URLs.");
        } else {
          setNote("Could not load your ingress URLs.");
        }
      });
  }, []);

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">ingress urls</div>
      {note && <p className="font-mono text-xs text-muted-foreground">{note}</p>}
      {!note && urls.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">
          No ingress URLs yet — create one from the desktop app.
        </p>
      )}
      {urls.length > 0 && (
        <ul className="divide-y divide-border">
          {urls.map((u) => (
            <li key={u.id} className="py-3">
              <div className="stamp text-[11px] uppercase text-muted-foreground">
                {u.integration}
              </div>
              <code className="mt-1 block break-all font-mono text-xs text-foreground">
                {u.url}
              </code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/components/DeliveryHistoryCard.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";

import { ApiException } from "@/lib/api";
import { listDeliveries, type Delivery } from "@/lib/api/installs";

export function DeliveryHistoryCard() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    listDeliveries(20)
      .then((r) => setDeliveries(r.deliveries))
      .catch((e) => {
        if (e instanceof ApiException && (e.code === "cloud_unavailable" || e.code === "no_tenant")) {
          setNote("Delivery history will appear once hosted ingress is connected.");
        } else {
          setNote("Could not load delivery history.");
        }
      });
  }, []);

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">recent deliveries</div>
      {note && <p className="font-mono text-xs text-muted-foreground">{note}</p>}
      {!note && deliveries.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">No deliveries yet.</p>
      )}
      {deliveries.length > 0 && (
        <ul className="divide-y divide-border">
          {deliveries.map((d) => (
            <li key={d.delivery_id} className="flex items-center justify-between py-2">
              <div className="min-w-0">
                <div className="stamp text-[11px] uppercase text-muted-foreground">
                  {d.integration} · {d.status}
                </div>
                <code className="block truncate font-mono text-[11px] text-foreground/70">
                  {d.delivery_id}
                </code>
              </div>
              <span className="stamp shrink-0 text-[11px] text-muted-foreground">
                {new Date(d.received_at).toLocaleTimeString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/dashboard/page.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";

import { AccountShell } from "@/components/AccountShell";
import { AccountTokenCard } from "@/components/AccountTokenCard";
import { DeliveryHistoryCard } from "@/components/DeliveryHistoryCard";
import { IngressUrlsCard } from "@/components/IngressUrlsCard";
import { InstallsCard } from "@/components/InstallsCard";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { createCheckoutSession, createPortalSession, getSubscription, type SubscriptionStatus } from "@/lib/api/billing";
import { useAuth } from "@/lib/auth-context";

const ENTITLED = new Set(["active", "trialing", "past_due"]);

export default function DashboardPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  const reload = useCallback(async () => {
    setStatus(await getSubscription());
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <AccountShell email={user?.email ?? ""}>
      <div className="briefing-in mb-8">
        <div className="briefing-label">hosted ingress</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Dashboard</h1>
      </div>

      <div className="space-y-6">
        <SubscriptionCard
          status={status}
          onSubscribe={async () => {
            const { url } = await createCheckoutSession();
            window.location.href = url;
          }}
          onManage={async () => {
            const { url } = await createPortalSession();
            window.location.href = url;
          }}
        />
        <AccountTokenCard
          entitled={ENTITLED.has(status?.status ?? "none")}
          issuedAt={status?.account_token_issued_at ?? null}
          onIssued={() => void reload()}
        />
        <InstallsCard />
        <IngressUrlsCard />
        <DeliveryHistoryCard />
      </div>
    </AccountShell>
  );
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/src/app/(authed)/billing/page.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";

import { AccountShell } from "@/components/AccountShell";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { createCheckoutSession, createPortalSession, getSubscription, type SubscriptionStatus } from "@/lib/api/billing";
import { useAuth } from "@/lib/auth-context";

export default function BillingPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  const reload = useCallback(async () => {
    setStatus(await getSubscription());
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <AccountShell email={user?.email ?? ""}>
      <div className="briefing-in mb-8">
        <div className="briefing-label">account · billing</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Billing</h1>
      </div>
      <SubscriptionCard
        status={status}
        onSubscribe={async () => {
          const { url } = await createCheckoutSession();
          window.location.href = url;
        }}
        onManage={async () => {
          const { url } = await createPortalSession();
          window.location.href = url;
        }}
      />
    </AccountShell>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/frontend && pnpm vitest run`
Expected: PASS — all frontend unit suites pass, "0 failed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add frontend/src
git commit -m "feat: add dashboard and billing pages with token, install and delivery cards"
```

---

### Task 32: Playwright happy-path e2e

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/dev/__init__.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/dev/router.py`
- Modify: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/playwright.config.ts`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_dev_routes.py`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/e2e/happy-path.spec.ts`

**Interfaces:**
- Consumes: `app.mailer.set_mailer`, `settings.ENV`.
- Produces: `RecordingMailer` installed when `ENV != "prod"`; `GET /api/v1/dev/last-verification-link?email=<email>` returning `{"link": str}` or `404 dev_routes_disabled` in prod.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/tests/integration/test_dev_routes.py`:

```python
import pytest

from app import mailer as mailer_mod
from app.api.v1.dev.router import RecordingMailer


@pytest.fixture
def recording() -> RecordingMailer:
    rec = RecordingMailer()
    mailer_mod.set_mailer(rec)
    yield rec
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


@pytest.mark.asyncio
async def test_returns_the_last_verification_link_for_an_email(client, recording) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "dev@example.com", "password": "correct-horse-battery-staple"},
    )
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "dev@example.com"})
    assert r.status_code == 200
    assert "verify-email?token=" in r.json()["link"]


@pytest.mark.asyncio
async def test_returns_404_for_an_unknown_email(client, recording) -> None:
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "nope@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_verification_link"


@pytest.mark.asyncio
async def test_dev_routes_are_disabled_in_prod(
    client, recording, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "dev@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "dev_routes_disabled"
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/e2e/happy-path.spec.ts`:

```ts
import { createHmac } from "node:crypto";

import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "https://api.saiife.localhost:8000";
const WEBHOOK_SECRET = process.env.E2E_STRIPE_WEBHOOK_SECRET ?? "whsec_test_secret";

function sign(body: string): string {
  const ts = Math.floor(Date.now() / 1000);
  const mac = createHmac("sha256", WEBHOOK_SECRET).update(`${ts}.${body}`).digest("hex");
  return `t=${ts},v1=${mac}`;
}

test("signup -> subscribe (stubbed Stripe) -> token issued -> visible in dashboard", async ({
  page,
  request,
}) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "correct-horse-battery-staple";

  // 1. Sign up.
  await page.goto("/signup");
  await page.getByRole("button", { name: "email" }).click();
  await page.getByLabel("email").fill(email);
  await page.getByLabel("password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(/check your inbox/i)).toBeVisible();

  // 2. Verify the email using the dev-only mail sink.
  const linkResponse = await request.get(
    `${API}/api/v1/dev/last-verification-link?email=${encodeURIComponent(email)}`,
  );
  expect(linkResponse.ok()).toBeTruthy();
  const { link } = (await linkResponse.json()) as { link: string };
  await page.goto(link);
  await expect(page).toHaveURL(/\/dashboard/);

  // 3. Subscribe. The backend's MockStripeGateway returns a non-navigable
  //    checkout URL, so block the navigation and drive the webhook ourselves —
  //    exactly what Stripe would send on a completed checkout.
  await page.route("**checkout.stripe.invalid/**", (route) => route.abort());
  await page.getByRole("button", { name: "Subscribe" }).click();

  const body = JSON.stringify({
    id: `evt_e2e_${Date.now()}`,
    type: "checkout.session.completed",
    data: {
      object: {
        customer: "cus_mock_1",
        subscription: `sub_e2e_${Date.now()}`,
        metadata: {},
      },
    },
  });
  const hook = await request.post(`${API}/api/v1/billing/webhook`, {
    data: body,
    headers: { "Stripe-Signature": sign(body), "Content-Type": "application/json" },
  });
  expect(hook.ok()).toBeTruthy();
  expect((await hook.json()).action).toBe("tenant_created");

  // 4. Issue the account token and confirm it is shown once, in the dashboard.
  await page.goto("/dashboard");
  await expect(page.getByText(/your subscription is active/i)).toBeVisible();
  await page.getByRole("button", { name: /issue account token/i }).click();
  const token = page.locator("code", { hasText: /^sfc_/ });
  await expect(token).toBeVisible();
  await expect(token).toHaveText(/^sfc_[0-9a-f]{18}_[A-Za-z0-9_-]+$/);

  // 5. Dismissing hides it, and it is never shown again on reload.
  await page.getByRole("button", { name: /i saved it/i }).click();
  await expect(token).toHaveCount(0);
  await page.reload();
  await expect(page.locator("code", { hasText: /^sfc_/ })).toHaveCount(0);
  await expect(page.getByText(/last issued/i)).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_dev_routes.py -q`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.api.v1.dev'"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/dev/router.py`:

```python
"""Dev-only helpers. Every handler refuses to run when ENV == "prod".

`RecordingMailer` keeps the last verification link per address in memory so the
Playwright e2e can complete the signup flow without a real inbox. Nothing here is
reachable in production, and it never exposes account tokens or password hashes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ....core.config import settings
from ....mailer import get_mailer

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


class RecordingMailer:
    def __init__(self) -> None:
        self.links: dict[str, str] = {}

    async def send_verification(self, email: str, link: str) -> None:
        self.links[email.lower()] = link


def _err(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/last-verification-link")
async def last_verification_link(email: str = Query(...)) -> dict[str, str]:
    if settings.ENV == "prod":
        raise _err("dev_routes_disabled", "Not found.", 404)
    mailer = get_mailer()
    links = getattr(mailer, "links", None)
    if not isinstance(links, dict):
        raise _err("no_verification_link", "No verification link was recorded.", 404)
    link = links.get(email.lower())
    if link is None:
        raise _err("no_verification_link", "No verification link was recorded.", 404)
    return {"link": link}
```

Modify `/home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/main.py` — install the recording mailer outside prod and register the router:

```python
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_default_mailer()
    if settings.ENV == "dev":
        # Dev only: keep verification links in memory so the e2e can read them.
        from .api.v1.dev.router import RecordingMailer
        from .mailer import set_mailer

        set_mailer(RecordingMailer())
    configure_default_cloud()
    configure_default_stripe_gateway()
    yield
```

```python
from app.api.v1.dev.router import router as dev_router  # noqa: E402

app.include_router(dev_router)
```

```bash
mkdir -p /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/dev
touch /home/jonasrobinson/projects/saiife/saiife-hub/backend/src/app/api/v1/dev/__init__.py
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3001",
    trace: "on-first-retry",
    ignoreHTTPSErrors: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.CI
    ? undefined
    : {
        command: "pnpm dev",
        url: process.env.E2E_BASE_URL ?? "http://localhost:3001",
        reuseExistingServer: true,
        timeout: 120_000,
        ignoreHTTPSErrors: true,
      },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/jonasrobinson/projects/saiife/saiife-hub/backend && uv run pytest tests/integration/test_dev_routes.py -q`
Expected: PASS — "3 passed"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/src/app/api/v1/dev backend/src/app/main.py backend/tests/integration/test_dev_routes.py frontend/playwright.config.ts frontend/e2e
git commit -m "test: add dev mail sink and the signup-to-token Playwright happy path"
```

---

### Task 33: Container images, compose, env template and Cloud Build

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/Dockerfile`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/Dockerfile.dev`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/backend/.env.example`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/frontend/Dockerfile`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/docker-compose.yml`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/cloudbuild.yaml`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-deploy.sh`

**Interfaces:**
- Consumes: `backend/pyproject.toml`, `frontend/package.json`, `pnpm-workspace.yaml`.
- Produces: images `backend` (port 8000) and `frontend` (port 3001); `docker compose up` running Postgres + both services; `cloudbuild.yaml` substitutions `_SHA`, `_REGION`, `_REPO`, `_API_HOST`.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-deploy.sh`:

```bash
#!/usr/bin/env bash
# Validates the deploy plumbing without building or pushing anything.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0

need_file() {
  [ -f "$ROOT/$1" ] || { echo "MISSING FILE: $1"; fail=1; }
}
need_text() {
  grep -q -- "$2" "$ROOT/$1" || { echo "MISSING IN $1: $2"; fail=1; }
}
forbid_text() {
  if grep -q -- "$2" "$ROOT/$1"; then echo "FORBIDDEN IN $1: $2"; fail=1; fi
}

need_file backend/Dockerfile
need_file backend/Dockerfile.dev
need_file backend/.env.example
need_file frontend/Dockerfile
need_file docker-compose.yml
need_file cloudbuild.yaml

need_text backend/Dockerfile 'PYTHONPATH=/app/src'
need_text backend/Dockerfile 'EXPOSE 8000'
need_text frontend/Dockerfile 'PORT=3001'
need_text frontend/Dockerfile 'NEXT_PUBLIC_API_URL'
need_text cloudbuild.yaml '_API_HOST'
need_text docker-compose.yml 'postgres:16-alpine'

# Public repo: the env template must never carry a usable secret.
forbid_text backend/.env.example 'sk_live'
forbid_text backend/.env.example 'whsec_live'
need_text backend/.env.example 'ACCOUNT_TOKEN_PEPPER=replace-me-locally-only'

if [ "$fail" -ne 0 ]; then
  echo "DEPLOY CHECK FAILED"
  exit 1
fi
echo "DEPLOY CHECK PASSED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-deploy.sh`
Expected: FAIL with "MISSING FILE: backend/Dockerfile" and "DEPLOY CHECK FAILED"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim AS builder
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src
USER appuser
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/Dockerfile.dev`:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
EXPOSE 8000
CMD ["uv","run","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--reload"]
```

`/home/jonasrobinson/projects/saiife/saiife-hub/backend/.env.example`:

```dotenv
# Local development template. NOTHING here is a real credential — this repo is public.
# Production values come from Secret Manager and are never committed.

DATABASE_URL=postgresql+asyncpg://saiife:dev@postgres:5432/saiife
ENV=dev
LOG_LEVEL=debug
APP_VERSION=dev

APP_URL=http://localhost:3001
MARKETING_URL=http://localhost:3000

APP_JWT_SECRET=replace-me-locally-only
COOKIE_DOMAIN=
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

PASSKEY_RP_ID=localhost
PASSKEY_RP_NAME=saiife
PASSKEY_ORIGIN=http://localhost:3001

GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

MAILGUN_API_KEY=
MAILGUN_DOMAIN=
MAILGUN_BASE_URL=https://api.eu.mailgun.net

# MUST equal saiife-cloud's pepper in every deployed environment.
# See docs/2026-07-21-saiife-cloud-admin-api-contract.md.
ACCOUNT_TOKEN_PEPPER=replace-me-locally-only

# Empty CLOUD_ADMIN_API_URL => the in-memory control plane. Leave it empty until
# saiife-cloud implements the admin API.
CLOUD_ADMIN_API_URL=
CLOUD_ADMIN_API_KEY=

# Empty STRIPE_SECRET_KEY => MockStripeGateway (no network).
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=whsec_test_secret
STRIPE_PRICE_ID=
STRIPE_SIGNATURE_TOLERANCE_SECONDS=300
```

`/home/jonasrobinson/projects/saiife/saiife-hub/frontend/Dockerfile`:

```dockerfile
# Build from the REPOSITORY ROOT: docker build -f frontend/Dockerfile .
FROM node:22-alpine AS deps
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
WORKDIR /usr/src/app
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY frontend/package.json ./frontend/
COPY packages/ui/package.json ./packages/ui/
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS build
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
WORKDIR /usr/src/app
COPY --from=deps /usr/src/app/node_modules ./node_modules
COPY --from=deps /usr/src/app/frontend/node_modules ./frontend/node_modules
COPY --from=deps /usr/src/app/packages/ui/node_modules ./packages/ui/node_modules
COPY . .
# NEXT_PUBLIC_* is INLINED at build time, so the API host is baked here and each
# environment builds its own image.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm --filter frontend build

FROM node:22-alpine AS runtime
WORKDIR /usr/src/app/frontend
ENV NODE_ENV=production PORT=3001 HOSTNAME=0.0.0.0
COPY --from=build /usr/src/app/frontend/.next/standalone /usr/src/app
COPY --from=build /usr/src/app/frontend/.next/static ./.next/static
USER node
EXPOSE 3001
CMD ["node", "server.js"]
```

`/home/jonasrobinson/projects/saiife/saiife-hub/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: saiife
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: saiife
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U saiife"]
      interval: 2s
      timeout: 2s
      retries: 30

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    environment:
      DATABASE_URL: postgresql+asyncpg://saiife:dev@postgres:5432/saiife
      ENV: dev
      LOG_LEVEL: debug
      APP_VERSION: dev
      APP_URL: http://localhost:3001
      MARKETING_URL: http://localhost:3000
      APP_JWT_SECRET: dev-only-not-secret
      COOKIE_DOMAIN: ""
      COOKIE_SECURE: "false"
      PASSKEY_RP_ID: localhost
      PASSKEY_ORIGIN: http://localhost:3001
      ACCOUNT_TOKEN_PEPPER: dev-only-not-secret
      CLOUD_ADMIN_API_URL: ""
      STRIPE_SECRET_KEY: ""
      STRIPE_WEBHOOK_SECRET: whsec_test_secret
      STRIPE_PRICE_ID: price_dev
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app
      - backend_uv_cache:/root/.cache/uv
    depends_on:
      postgres:
        condition: service_healthy

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    ports: ["3001:3001"]
    depends_on: [backend]

volumes:
  pgdata: {}
  backend_uv_cache: {}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/cloudbuild.yaml`:

```yaml
# Builds and pushes the two saiife-hub images.
#   gcloud builds submit --config=cloudbuild.yaml \
#     --substitutions=_SHA=<git sha>,_REGION=<region>,_REPO=<repo>,_API_HOST=<api host>
steps:
  - id: build-backend
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -f
      - backend/Dockerfile
      - -t
      - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/backend:${_SHA}"
      - backend
    waitFor: ["-"]

  - id: build-frontend
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - --build-arg
      - "NEXT_PUBLIC_API_URL=https://${_API_HOST}"
      - -f
      - frontend/Dockerfile
      - -t
      - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/frontend:${_SHA}"
      - .
    waitFor: ["-"]

  - id: push-backend
    name: gcr.io/cloud-builders/docker
    args: [push, "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/backend:${_SHA}"]
    waitFor: [build-backend]

  - id: push-frontend
    name: gcr.io/cloud-builders/docker
    args: [push, "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/frontend:${_SHA}"]
    waitFor: [build-frontend]

images:
  - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/backend:${_SHA}"
  - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/frontend:${_SHA}"

options:
  machineType: E2_HIGHCPU_8
  logging: CLOUD_LOGGING_ONLY

timeout: 1800s

# No real project id, region or host is committed — every substitution must be
# supplied at submit time. This repo is public.
substitutions:
  _SHA: latest
  _REGION: europe-west1
  _REPO: app
  _API_HOST: api.example.invalid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-deploy.sh`
Expected: PASS — prints "DEPLOY CHECK PASSED"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add backend/Dockerfile backend/Dockerfile.dev backend/.env.example frontend/Dockerfile docker-compose.yml cloudbuild.yaml scripts/check-deploy.sh
git commit -m "chore: add container images, compose stack, env template and Cloud Build config"
```

---

### Task 34: Terraform — authored, not applied

**Files:**
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/main.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/variables.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/01_artifact_registry.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/02_database.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/03_secrets.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/04_run_services.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/05_run_migrate_job.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/06_iam.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/outputs.tf`
- Create: `/home/jonasrobinson/projects/saiife/saiife-hub/infra/README.md`
- Test: `/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-infra.sh`

**Interfaces:**
- Consumes: `cloudbuild.yaml` image paths.
- Produces: Terraform for Artifact Registry, Cloud SQL Postgres 16, Secret Manager containers, Cloud Run ×2, a migrate job, and IAM. No `terraform apply` anywhere.

- [ ] **Step 1: Write the failing test**

`/home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-infra.sh`:

```bash
#!/usr/bin/env bash
# Terraform is AUTHORED here, never applied. This check enforces the public-repo
# rules: no real project ids or hostnames, no secret VALUES, and no apply step.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA="$ROOT/infra"
fail=0

for f in main.tf variables.tf 01_artifact_registry.tf 02_database.tf 03_secrets.tf \
         04_run_services.tf 05_run_migrate_job.tf 06_iam.tf outputs.tf README.md; do
  [ -f "$INFRA/$f" ] || { echo "MISSING FILE: infra/$f"; fail=1; }
done

# Environment-identifying variables must be REQUIRED (no default) so nothing real
# is committed.
for var in project_id region base_domain; do
  if ! grep -A4 "variable \"$var\"" "$INFRA/variables.tf" | grep -q "REQUIRED"; then
    echo "variable $var must be documented REQUIRED with no default"; fail=1
  fi
  if grep -A4 "variable \"$var\"" "$INFRA/variables.tf" | grep -q "default"; then
    echo "variable $var must NOT have a default"; fail=1
  fi
done

# Never a secret VALUE in Terraform — containers only.
if grep -rn "secret_data" "$INFRA" | grep -v "^.*#" | grep -q .; then
  echo "FORBIDDEN: infra must create secret CONTAINERS only, never versions"; fail=1
fi

# No apply automation may exist in this repo. This checker is excluded because it
# necessarily contains the very string it searches for.
if grep -rln "terraform apply" "$ROOT" \
     --include="*.sh" --include="*.yaml" --include="*.yml" --include="Makefile" \
     --exclude="check-infra.sh" | grep -q .; then
  echo "FORBIDDEN: this round authors Terraform, it never applies it"; fail=1
fi

grep -q "authored" "$INFRA/README.md" || { echo "README must state infra is authored, not applied"; fail=1; }

if [ "$fail" -ne 0 ]; then
  echo "INFRA CHECK FAILED"
  exit 1
fi
echo "INFRA CHECK PASSED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-infra.sh`
Expected: FAIL with "MISSING FILE: infra/main.tf" and "INFRA CHECK FAILED"

- [ ] **Step 3: Write minimal implementation**

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/main.tf`:

```hcl
terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # The state bucket is supplied at init time:
  #   terraform init -backend-config="bucket=<your-tfstate-bucket>"
  backend "gcs" {
    prefix = "hub"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/variables.tf`:

```hcl
# REQUIRED — no default. This repo is public; nothing that names real
# infrastructure is committed. Supply via TF_VAR_project_id.
variable "project_id" {
  type        = string
  description = "REQUIRED. GCP project id. Never committed."
}

# REQUIRED — no default. europe-west1 to sit alongside saiife-cloud.
variable "region" {
  type        = string
  description = "REQUIRED. GCP region, e.g. europe-west1. Never committed."
}

# REQUIRED — no default. Drives every URL and the cookie domain.
variable "base_domain" {
  type        = string
  description = "REQUIRED. Public base domain, e.g. hub.example.com. Never committed."
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "artifact_repo" {
  type    = string
  default = "app"
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

# Image refs are set per-deploy by the pipeline, never via tfvars. The first
# apply uses the placeholder so Cloud Run resources exist before any real image.
variable "backend_image" {
  type    = string
  default = "gcr.io/cloudrun/hello"
}

variable "frontend_image" {
  type    = string
  default = "gcr.io/cloudrun/hello"
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/01_artifact_registry.tf`:

```hcl
resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "saiife-hub container images"
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/02_database.tf`:

```hcl
resource "random_password" "db_password" {
  length  = 32
  special = false # avoids quoting headaches in the connection string
}

resource "google_sql_database_instance" "main" {
  name             = "saiife-hub-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    ip_configuration {
      # A public IP exists, but with NO authorized_networks the instance is not
      # reachable from the internet. Cloud Run's Cloud SQL Auth Proxy is the only
      # path, authenticated by the runtime SA's cloudsql.client role.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "hub" {
  name     = "saiife_hub"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "hub" {
  name     = "saiife"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/03_secrets.tf`:

```hcl
# Terraform manages secret CONTAINERS ONLY. Values are added out of band with
#   gcloud secrets versions add <name> --data-file=-
# so no secret material ever passes through Terraform, state, or this repo.
#
# account-token-pepper MUST hold the SAME value as saiife-cloud's pepper — see
# docs/2026-07-21-saiife-cloud-admin-api-contract.md.
locals {
  backend_secret_ids = [
    "database-url",
    "app-jwt-secret",
    "account-token-pepper",
    "cloud-admin-api-key",
    "stripe-secret-key",
    "stripe-webhook-secret",
    "google-oauth-client-id",
    "google-oauth-client-secret",
    "mailgun-api-key",
  ]
}

resource "google_secret_manager_secret" "backend" {
  for_each  = toset(local.backend_secret_ids)
  secret_id = each.value

  replication {
    auto {}
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/04_run_services.tf`:

```hcl
locals {
  services = {
    backend  = { port = 8000, image = var.backend_image }
    frontend = { port = 3001, image = var.frontend_image }
  }

  # Non-secret backend config, derived from environment + base_domain.
  backend_env = {
    APP_VERSION               = var.environment
    ENV                       = var.environment
    LOG_LEVEL                 = "info"
    COOKIE_DOMAIN             = ".${var.base_domain}"
    COOKIE_SECURE             = "true"
    APP_URL                   = "https://app.${var.base_domain}"
    MARKETING_URL             = "https://${var.base_domain}"
    PASSKEY_RP_ID             = var.base_domain
    PASSKEY_RP_NAME           = "saiife"
    PASSKEY_ORIGIN            = "https://app.${var.base_domain}"
    GOOGLE_OAUTH_REDIRECT_URI = "https://api.${var.base_domain}/api/v1/auth/google/callback"
    MAILGUN_DOMAIN            = "mg.${var.base_domain}"
    MAILGUN_FROM              = "saiife <noreply@${var.base_domain}>"
    MAILGUN_BASE_URL          = "https://api.eu.mailgun.net"
    # Left EMPTY until saiife-cloud implements the admin API. Empty means the
    # backend keeps using the in-memory control plane and never calls out.
    CLOUD_ADMIN_API_URL = ""
  }

  backend_secret_envs = {
    DATABASE_URL                = "database-url"
    APP_JWT_SECRET              = "app-jwt-secret"
    ACCOUNT_TOKEN_PEPPER        = "account-token-pepper"
    CLOUD_ADMIN_API_KEY         = "cloud-admin-api-key"
    STRIPE_SECRET_KEY           = "stripe-secret-key"
    STRIPE_WEBHOOK_SECRET       = "stripe-webhook-secret"
    GOOGLE_OAUTH_CLIENT_ID      = "google-oauth-client-id"
    GOOGLE_OAUTH_CLIENT_SECRET  = "google-oauth-client-secret"
    MAILGUN_API_KEY             = "mailgun-api-key"
  }
}

resource "google_service_account" "service_sa" {
  for_each     = local.services
  account_id   = "saiife-hub-${each.key}-sa"
  display_name = "Cloud Run runtime SA for saiife-hub-${each.key}"
}

resource "google_cloud_run_v2_service" "service" {
  for_each = local.services
  name     = "saiife-hub-${each.key}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.service_sa[each.key].email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = each.value.image

      ports {
        container_port = each.value.port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = each.key == "backend" ? local.backend_env : {}
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "backend" ? local.backend_secret_envs : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.backend[env.value].secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "volume_mounts" {
        for_each = each.key == "backend" ? toset(["cloudsql"]) : toset([])
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }

    dynamic "volumes" {
      for_each = each.key == "backend" ? toset(["cloudsql"]) : toset([])
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
    }
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/05_run_migrate_job.tf`:

```hcl
# Runs `alembic upgrade head` against Cloud SQL. Executed by the deploy pipeline
# before traffic is shifted; never executed by Terraform itself.
resource "google_cloud_run_v2_job" "migrate" {
  name     = "saiife-hub-migrate"
  location = var.region

  template {
    template {
      service_account = google_service_account.service_sa["backend"].email

      containers {
        image   = var.backend_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.backend["database-url"].secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
    }
  }
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/06_iam.tf`:

```hcl
# The backend SA may read its own secrets and reach Cloud SQL. The frontend SA
# gets neither — it holds no secrets and never touches the database.
resource "google_secret_manager_secret_iam_member" "backend_accessor" {
  for_each  = google_secret_manager_secret.backend
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.service_sa["backend"].email}"
}

resource "google_project_iam_member" "backend_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.service_sa["backend"].email}"
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/outputs.tf`:

```hcl
output "backend_url" {
  value = google_cloud_run_v2_service.service["backend"].uri
}

output "frontend_url" {
  value = google_cloud_run_v2_service.service["frontend"].uri
}

output "sql_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "artifact_repository" {
  value = google_artifact_registry_repository.app.name
}
```

`/home/jonasrobinson/projects/saiife/saiife-hub/infra/README.md`:

```markdown
# infra — authored, not applied

This Terraform is **authored** in this round and has never been applied. There is
no apply step in any script, Makefile target, or CI config in this repository,
and adding one is out of scope.

## Why it is not applied

saiife-hub cannot go live until saiife-cloud is wired: `CLOUD_ADMIN_API_URL` is
deliberately empty, so a deployed backend would run against the in-memory control
plane and issue tokens no relay can verify. Wiring saiife-cloud is separate,
later work.

## What it describes

| File | Resource |
|---|---|
| `01_artifact_registry.tf` | Docker repository for the two images |
| `02_database.tf` | Cloud SQL Postgres 16, database, user |
| `03_secrets.tf` | Secret Manager **containers** — values are added out of band |
| `04_run_services.tf` | Cloud Run ×2 (backend :8000, frontend :3001) and their SAs |
| `05_run_migrate_job.tf` | Cloud Run job running `alembic upgrade head` |
| `06_iam.tf` | Secret accessor + Cloud SQL client for the backend SA only |

## Public-repo rules enforced by `scripts/check-infra.sh`

- `project_id`, `region` and `base_domain` are **required** with no defaults.
  Supply them via `TF_VAR_*`; nothing real is committed.
- Terraform creates secret containers only, never secret versions, so no secret
  material passes through state.
- No `terraform apply` appears anywhere in the repository.

## The pepper

`account-token-pepper` must hold the **same value** as saiife-cloud's pepper.
Account tokens hub issues are verified by cloud against that shared value; see
`docs/2026-07-21-saiife-cloud-admin-api-contract.md`. Rotating it invalidates
every issued token.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash /home/jonasrobinson/projects/saiife/saiife-hub/scripts/check-infra.sh`
Expected: PASS — prints "INFRA CHECK PASSED"

- [ ] **Step 5: Commit**

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
git add infra scripts/check-infra.sh
git commit -m "chore: author Cloud Run, Cloud SQL and Secret Manager Terraform (not applied)"
```

---

## Final verification

Run every check in one pass before declaring the build complete:

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
bash scripts/check-layout.sh
bash scripts/check-deploy.sh
bash scripts/check-infra.sh
cd backend && uv run pytest -q && uv run ruff check . && uv run mypy src
cd ../frontend && pnpm vitest run && pnpm exec tsc --noEmit
```

Everything above runs with **no GCP account and no network**: the database is
sqlite, the cloud control plane is `InMemoryCloudControlPlane`, Stripe is
`MockStripeGateway`, and email is `RecordingMailer`/`ConsoleMailer`.

The Playwright e2e needs the compose stack:

```bash
cd /home/jonasrobinson/projects/saiife/saiife-hub
docker compose up -d
cd frontend && pnpm exec playwright test
```

## Spec coverage

| Spec section | Covering tasks |
|---|---|
| The money path (signup → subscribe → tenant → token → dashboard) | 9, 23, 24, 25, 31, 32 |
| Architecture split (Next.js UI only, FastAPI computes) | 1, 2, 27, 28 |
| Ported frontend: login, signup, verify-email, oauth-callback | 29 |
| Ported frontend: `(authed)` layout and shell | 30 |
| Ported frontend: `settings/security` passkeys | 30 |
| Dropped scan/PR surface (never created) | 27–31 |
| Ported backend `auth/` (argon2id, JWT, CSRF, OAuth, passkeys, refresh rotation) | 5, 6, 7, 9, 10, 11, 12 |
| Ported app boot, structlog, rate limiting, error taxonomy | 2 |
| Ported Alembic setup | 4, 19 |
| Brand layer copy | 27 |
| Billing: checkout, portal, signature-verified idempotent webhook | 20, 21, 22, 23, 24 |
| Tenant creation/deletion and `sfc_` token minting | 13–18, 22, 25 |
| Installs: link, list, proxy ingress URLs and deliveries | 26 |
| Dashboard replacing the dropped domain dashboard | 31 |
| The saiife-cloud seam: interface, mock, deferred HTTP, docs deliverable | 13, 14, 15, 16 |
| Security: hashed-only secrets, signature verification, argon2id/CSRF/replay, no enumeration oracle, rate limits, Secret Manager | 5, 7, 9, 10, 17, 18, 20, 24, 25, 34 |
| Public-repo rule: no real project ids, endpoints or peppers | 33, 34 |
| Testing: pytest unit + integration, offline coverage, replay/idempotency, Vitest, one Playwright e2e | 5–32 |
| Deployment: Terraform, Cloud Run ×2, Cloud SQL, Secret Manager, authored not applied | 33, 34 |
| Sequencing: hub cannot go live until cloud is wired | 15, 34 |





