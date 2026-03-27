terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required APIs ──────────────────────────────────────────────────────

resource "google_project_service" "run_api" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "registry_api" {
  service            = "containerregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage_api" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam_api" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iamcredentials_api" {
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

# ── GCS Bucket ───────────────────────────────────────────────────────────────

resource "google_storage_bucket" "flood_risk" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# Make bucket publicly readable
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.flood_risk.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ── Service Account for GitHub Actions ───────────────────────────────────────

resource "google_service_account" "github_pipeline" {
  account_id   = "github-pipeline"
  display_name = "GitHub Actions Pipeline"
}

resource "google_project_iam_member" "run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

resource "google_project_iam_member" "secretmanager_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

resource "google_project_iam_member" "artifactregistry_admin" {
  project = var.project_id
  role    = "roles/artifactregistry.admin"
  member  = "serviceAccount:${google_service_account.github_pipeline.email}"
}

# ── Workload Identity Federation ─────────────────────────────────────────────

resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions OIDC"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository_owner == '${var.github_username}'"
}

resource "google_service_account_iam_member" "workload_identity_binding" {
  service_account_id = google_service_account.github_pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_username}/${var.github_repo}"
}

# ── Cloud Run — TiTiler Tile Server ──────────────────────────────────────────
# This is the only resource that incurs cost when running.
# Run `terraform destroy` to shut it down and avoid charges.
# Run `terraform apply` to bring it back when needed.

resource "google_cloud_run_v2_service" "titiler" {
  name     = "titiler"
  location = var.region

  depends_on = [google_project_service.run_api]

  template {
    containers {
      image = var.titiler_image

      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }

      env {
        name  = "GCS_BUCKET"
        value = var.bucket_name
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }
}

# Allow unauthenticated access to TiTiler
resource "google_cloud_run_service_iam_member" "titiler_public" {
  location = google_cloud_run_v2_service.titiler.location
  service  = google_cloud_run_v2_service.titiler.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
