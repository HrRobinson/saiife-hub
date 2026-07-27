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
       N=16384, r=8, p=1, dklen=32)
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
