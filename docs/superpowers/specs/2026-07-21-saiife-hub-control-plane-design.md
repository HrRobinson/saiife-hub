# saiife-hub — control plane design

**Status:** Design (spec) — not started
**Date:** 2026-07-21
**Repo:** `HrRobinson/saiife-hub` (public, currently empty)

## Purpose

The customer-facing control plane for saiife's paid hosted tier. This is where monetization actually happens.

The split, decided deliberately:

> **hub = who you are and what you pay. cloud = moving webhooks.**

`saiife-cloud` (private) is the data plane — a dumb-pipe webhook relay that resolves a tenant, rate-limits, and republishes to Pub/Sub. It holds no accounts and no billing. `saiife-hub` (public) owns identity, subscriptions, and the account tokens that let a desktop install talk to the relay at all.

## The money path

This is the flow the whole repo exists to serve:

1. User signs up on hub
2. User subscribes via Stripe
3. On successful payment, hub **provisions a tenant** in saiife-cloud
4. Hub issues an **account token** (`sfc_<lookupId>_<secret>`) and shows it once
5. User pastes the token into the saiife desktop app
6. The app calls cloud's control-api to create ingress URLs and mint drain tokens
7. User points a vendor webhook at `https://wh.saiife.cloud/wh/:ingressId`
8. Webhooks reach a laptop behind NAT. That is the product.

Steps 3 and 4 are the ones that do not exist anywhere yet. They are the core of this build.

## Architecture

Mirrors `saiife.com-old`'s proven split, per the explicit decision that **everything computational lives in a separate FastAPI backend**:

```
saiife-hub/
  frontend/    Next.js 16 · React 19 · Tailwind v4   — UI only, no business logic
  backend/     FastAPI · Python 3.12 · uv            — auth, billing, provisioning
  packages/ui/ shared brand layer                     — copied from saiife.com-old
  infra/       Terraform                              — Cloud Run ×2, Cloud SQL, secrets
```

The frontend renders and calls the backend. Anything computational — hashing, token minting, Stripe webhook verification, cloud provisioning — happens in FastAPI.

## What ports from `saiife.com-old`

### Frontend (`app/` → `frontend/`)

**Keep:**
- `(public)/login`, `(public)/signup`, `(public)/verify-email`, `(public)/oauth-callback`
- `(authed)` layout and shell — sidebar, nav, page chrome
- `(authed)/settings/security` — passkey management
- The shadcn component set in `packages/ui/src/components/ui/`

**Drop entirely** — all of it is scan/PR product surface:
- `(authed)/dashboard/[domain]/*` (overview, pulls, findings, agent, connections, settings)
- `(authed)/connections/github/callback`
- `(authed)/dashboard/domains`, `(authed)/dashboard/onboarding` (rebuilt, see below)

### Backend (`backend/src/app/`)

**Keep, verbatim where possible** — this is proven, tested, security-critical code and the reason FastAPI was chosen:
- `auth/` (468 lines) — argon2id, JWT cookies, CSRF, Google OAuth, `py_webauthn` passkeys, refresh-token rotation with replay lockdown
- The app boot, structlog config, rate-limiting middleware, and error taxonomy from `main.py`
- Alembic setup

**Drop:** `scanner/`, `github/`, `ai/`, `pulls/`, `connections/`, and every domain-posture model.

### Brand layer

Copy `tokens.css`, `tailwind.preset.ts`, ClashDisplay, `GradientButton`, `Eyebrow`, `RingIconBadge`, `SpotlightCard` from `saiife.com-old/packages/ui/`. These are byte-identical to the copies in `saiife.com` — that is the agreed sharing model. Each repo owns its own shadcn components; only the brand layer is duplicated.

## New surface

### Billing (`backend/src/app/billing/`)

Stripe subscriptions. Checkout session creation, customer portal links, and a **signature-verified webhook handler** driving subscription state.

Subscription state is the authority for whether a tenant exists in cloud. `checkout.session.completed` provisions; `customer.subscription.deleted` deprovisions. Handlers must be **idempotent** — Stripe retries, and double-provisioning a tenant is a real failure mode.

### Tenant provisioning (`backend/src/app/tenants/`)

Creates and destroys tenants in saiife-cloud, and mints the `sfc_` account tokens that cloud's control-api authenticates against.

Token format is pinned by `saiife-cloud/packages/shared/src/ids.ts`: **`sfc_<tenantLookupId>_<secret>`**, where `<secret>` is 32 random bytes and `ACCOUNT_TOKEN_PREFIX = 'sfc_'`. Cloud verifies with scrypt against a peppered hash, using dummy-hash timing equalization. **Hub must match that contract exactly** — read the cloud repo's `ids.ts` and `control-api/src/auth.ts` before writing a line of this. Show the secret once, store only the hash.

> **Vocabulary warning.** Cloud already uses "provision" to mean *Pub/Sub subscription* provisioning — see `SubscriptionProvisioner` and `GcpSubscriptionProvisioner` in `packages/control-api/`. That is a different thing from creating a tenant. Do not reuse the word ambiguously; prefer `createTenant` / `deleteTenant` in hub's own interfaces to avoid a collision that will confuse both codebases.

### Installs (`backend/src/app/installs/`)

Links a desktop install to an account. Lists ingress URLs and recent delivery history by proxying cloud's control-api (`GET/POST /v1/ingress-urls`).

### Dashboard (`frontend`)

Replaces the dropped domain dashboard: subscription status, account token issuance and rotation, connected installs, ingress URLs, and recent deliveries.

## The saiife-cloud seam — read this before building

**saiife-cloud is not being modified in this round, and it does not currently work.** Every GCP transport in it throws `NotWiredError` and its Terraform has never been applied.

Its control-api exposes exactly two routes — `/v1/ingress-urls` and `/v1/drain-token` — both authenticated as an existing tenant. **There is no route that creates one.** Cloud reads tenants from a `TenantStore` that nothing writes to. Someone has to write that record, and this repo is that someone; the contract for doing so does not exist yet and must be designed here.

Therefore hub must **not** hard-depend on a live cloud. Follow the pattern cloud itself already uses (`packages/shared/src/seams.ts`, `mocks.ts`):

1. Define a `CloudControlPlane` interface — `createTenant`, `deleteTenant`, `listIngressUrls`, `getDeliveryHistory`.
2. Ship an in-memory mock implementation. All tests run against it, fully offline.
3. Ship a real HTTP implementation that throws a loud `NotWiredError` until the cloud contract lands.
4. **Write the proposed admin-API contract into `docs/`** as the deliverable that saiife-cloud will implement.

Everything in this repo must be buildable and testable with no GCP account and no network.

## Security requirements

Non-negotiable, and mostly inherited from code that already gets this right:

- Account token secrets stored hashed only, never logged, never returned after creation
- Stripe webhooks signature-verified before any state change
- Auth flows keep argon2id, CSRF protection, and refresh-token replay lockdown intact
- Byte-identical responses on unknown-account lookups — no enumeration oracle
- Rate limiting on auth and token endpoints
- Secrets from Secret Manager, never committed

Since this repo is **public**, no real project IDs, endpoints, or pepper values in committed config.

## Testing

- **Backend:** pytest, mirroring the old repo's `tests/unit` + `tests/integration` layout. Port the auth test suite alongside the auth code. Full offline coverage of billing state transitions and provisioning against the mock. Explicitly test webhook idempotency and replay.
- **Frontend:** Vitest units, one Playwright happy-path e2e (signup → subscribe with a stubbed Stripe → token issued → visible in dashboard).

## Deployment

Terraform in `infra/`, following `saiife.com-old/infra/prod/`: Cloud Run ×2 (frontend, backend), Cloud SQL Postgres, Secret Manager, `europe-west1` to sit alongside saiife-cloud. Authored this round; applying is out of scope.

## Sequencing note

Hub can be built and fully tested now against mocks, but **cannot go live until saiife-cloud is wired**. Wiring cloud is a separate, later piece of work. Do not let this repo's agent attempt it.

## Open questions

- **The cloud admin-API contract.** Hub needs a way to provision tenants; cloud offers none today. This spec's answer is to define the contract here and stub it. If a different mechanism is preferred (hub writing Firestore directly, or extending control-api), that decision belongs with saiife-cloud, not here.
- **Pricing model** — per-seat, per-install, or flat. Not needed to build the plumbing; needed before launch.
