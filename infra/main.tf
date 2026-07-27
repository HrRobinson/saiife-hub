terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # The state bucket is supplied at init time:
  #   terraform init -backend-config="bucket=<your-tfstate-bucket>"
  backend "gcs" {
    prefix = "hub"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
