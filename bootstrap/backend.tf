# Remote state for this stack, after the storage account exists.
# Blob key: bootstrap.tfstate. Account coordinates come from backend.hcl.
#
# The first apply cannot use this backend (the account does not exist yet).
# Move this file aside, apply with the local backend, move it back, then migrate:
#
#   Rename-Item -Path backend.tf -NewName backend.tf.disabled
#   terraform init -reconfigure
#   terraform apply
#   Rename-Item -Path backend.tf.disabled -NewName backend.tf
#   ..\scripts\migrate-bootstrap-state.ps1
#
# `terraform init -backend=false` is for validate only. plan/apply will not run
# until the backend is initialized.
terraform {
  backend "azurerm" {
    key = "bootstrap.tfstate"
  }
}
