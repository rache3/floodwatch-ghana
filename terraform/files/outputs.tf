output "bucket_name" {
  description = "GCS bucket name"
  value       = google_storage_bucket.flood_risk.name
}

output "bucket_url" {
  description = "Public GCS bucket URL"
  value       = "https://storage.googleapis.com/${google_storage_bucket.flood_risk.name}"
}

output "titiler_url" {
  description = "TiTiler Cloud Run service URL — update this in docs/index.html"
  value       = google_cloud_run_v2_service.titiler.uri
}

output "workload_identity_provider" {
  description = "Workload Identity provider path — add this as a GitHub repo variable"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "service_account_email" {
  description = "GitHub Actions service account email — add this as a GitHub repo variable"
  value       = google_service_account.github_pipeline.email
}

output "next_steps" {
  description = "What to do after terraform apply"
  value       = <<-EOT
    1. Copy the titiler_url above into docs/index.html (TITILER_URL variable)
    2. Add these GitHub repo variables:
       - WORKLOAD_IDENTITY_PROVIDER = (workload_identity_provider output above)
       - SERVICE_ACCOUNT = (service_account_email output above)
       - GCP_PROJECT_ID = ${var.project_id}
       - GCP_PROJECT_NUMBER = ${var.project_number}
       - GCP_REGION = ${var.region}
       - GCS_BUCKET = ${var.bucket_name}
    3. To shut down and avoid charges: terraform destroy
    4. To bring back: terraform apply
  EOT
}
