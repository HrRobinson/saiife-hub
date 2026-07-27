resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "saiife-hub container images"
}
