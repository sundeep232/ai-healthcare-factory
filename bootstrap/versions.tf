terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.30, < 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # NOTE: bootstrap uses LOCAL state on purpose. It creates the storage account
  # that all other (per-instance) Terraform will use as its remote backend, so it
  # cannot depend on that backend itself. Local state files are git-ignored.
}
