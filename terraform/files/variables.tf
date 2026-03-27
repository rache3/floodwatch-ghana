variable "project_id" {
  description = "Your GCP project ID"
  type        = string
}

variable "project_number" {
  description = "Your GCP project number"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "github_username" {
  description = "Your GitHub username"
  type        = string
}

variable "github_repo" {
  description = "Your GitHub repository name"
  type        = string
}

variable "bucket_name" {
  description = "Name for the GCS bucket"
  type        = string
  default     = "accra-flood-risk"
}

variable "titiler_image" {
  description = "Full GCR image path for TiTiler"
  type        = string
}
