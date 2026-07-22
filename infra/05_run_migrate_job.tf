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
