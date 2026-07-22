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
