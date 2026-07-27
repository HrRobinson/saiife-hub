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
