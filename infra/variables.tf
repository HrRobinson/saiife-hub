# REQUIRED — no default. This repo is public; nothing that names real
# infrastructure is committed. Supply via TF_VAR_project_id.
variable "project_id" {
  type        = string
  description = "REQUIRED. GCP project id. Never committed."
}

# REQUIRED — no default. europe-west1 to sit alongside saiife-cloud.
variable "region" {
  type        = string
  description = "REQUIRED. GCP region, e.g. europe-west1. Never committed."
}

# REQUIRED — no default. Drives every URL and the cookie domain.
variable "base_domain" {
  type        = string
  description = "REQUIRED. Public base domain, e.g. hub.example.com. Never committed."
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "artifact_repo" {
  type    = string
  default = "app"
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

# Image refs are set per-deploy by the pipeline, never via tfvars. The first
# apply uses the placeholder so Cloud Run resources exist before any real image.
variable "backend_image" {
  type    = string
  default = "gcr.io/cloudrun/hello"
}

variable "frontend_image" {
  type    = string
  default = "gcr.io/cloudrun/hello"
}
