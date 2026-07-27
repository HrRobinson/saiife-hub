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
