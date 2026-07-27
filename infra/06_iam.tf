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
