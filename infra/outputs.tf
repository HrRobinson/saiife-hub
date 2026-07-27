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
