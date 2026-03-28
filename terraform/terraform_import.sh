#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# terraform_import.sh
# Imports all existing GCP resources into Terraform state
# Run this ONCE from inside the terraform/ folder
# ─────────────────────────────────────────────────────────────────────────────

set -e

PROJECT_ID="project-a93d8eb8-d695-49f7-857"
PROJECT_NUMBER="244163528833"
REGION="us-central1"
BUCKET="accra-flood-risk"
SA_EMAIL="github-pipeline@project-a93d8eb8-d695-49f7-857.iam.gserviceaccount.com"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         Terraform State Import — Flood Risk Pipeline        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Importing existing GCP resources into Terraform state..."
echo ""

# ── APIs ──────────────────────────────────────────────────────────────────────
echo "► Importing enabled APIs..."
terraform import google_project_service.run_api "$PROJECT_ID/run.googleapis.com"
terraform import google_project_service.registry_api "$PROJECT_ID/containerregistry.googleapis.com"
terraform import google_project_service.storage_api "$PROJECT_ID/storage.googleapis.com"
terraform import google_project_service.iam_api "$PROJECT_ID/iam.googleapis.com"
terraform import google_project_service.iamcredentials_api "$PROJECT_ID/iamcredentials.googleapis.com"
echo "  APIs imported ✓"

# ── GCS Bucket ────────────────────────────────────────────────────────────────
echo "► Importing GCS bucket..."
terraform import google_storage_bucket.flood_risk "$BUCKET"
echo "  Bucket imported ✓"

# ── Bucket IAM ────────────────────────────────────────────────────────────────
echo "► Importing bucket public access..."
terraform import google_storage_bucket_iam_member.public_read "$BUCKET roles/storage.objectViewer allUsers"
echo "  Bucket IAM imported ✓"

# ── Service Account ───────────────────────────────────────────────────────────
echo "► Importing service account..."
terraform import google_service_account.github_pipeline "projects/$PROJECT_ID/serviceAccounts/$SA_EMAIL"
echo "  Service account imported ✓"

# ── Project IAM Bindings ──────────────────────────────────────────────────────
echo "► Importing IAM bindings..."
terraform import google_project_iam_member.run_admin "$PROJECT_ID roles/run.admin serviceAccount:$SA_EMAIL"
terraform import google_project_iam_member.storage_admin "$PROJECT_ID roles/storage.admin serviceAccount:$SA_EMAIL"
terraform import google_project_iam_member.secretmanager_accessor "$PROJECT_ID roles/secretmanager.secretAccessor serviceAccount:$SA_EMAIL"
terraform import google_project_iam_member.artifactregistry_admin "$PROJECT_ID roles/artifactregistry.admin serviceAccount:$SA_EMAIL"
echo "  IAM bindings imported ✓"

# ── Workload Identity Pool ────────────────────────────────────────────────────
echo "► Importing Workload Identity pool..."
terraform import google_iam_workload_identity_pool.github_pool "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool"
echo "  Pool imported ✓"

# ── Workload Identity Provider ────────────────────────────────────────────────
echo "► Importing Workload Identity provider..."
terraform import google_iam_workload_identity_pool_provider.github_provider "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "  Provider imported ✓"

# ── Service Account IAM ───────────────────────────────────────────────────────
echo "► Importing Workload Identity binding..."
terraform import google_service_account_iam_member.workload_identity_binding \
  "projects/$PROJECT_ID/serviceAccounts/$SA_EMAIL roles/iam.workloadIdentityUser principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/rache3/flood-risk-mapping-greater-accra"
echo "  Binding imported ✓"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              All resources imported ✓                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Now run: terraform plan"
echo "It should show 1 resource to add (Cloud Run) and 0 to change."
echo ""
