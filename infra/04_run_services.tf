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
    DATABASE_URL               = "database-url"
    APP_JWT_SECRET             = "app-jwt-secret"
    ACCOUNT_TOKEN_PEPPER       = "account-token-pepper"
    CLOUD_ADMIN_API_KEY        = "cloud-admin-api-key"
    STRIPE_SECRET_KEY          = "stripe-secret-key"
    STRIPE_WEBHOOK_SECRET      = "stripe-webhook-secret"
    GOOGLE_OAUTH_CLIENT_ID     = "google-oauth-client-id"
    GOOGLE_OAUTH_CLIENT_SECRET = "google-oauth-client-secret"
    MAILGUN_API_KEY            = "mailgun-api-key"
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
