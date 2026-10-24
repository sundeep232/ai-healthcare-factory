provider "azurerm" {
  # azurerm v4 requires an explicit subscription (no implicit default).
  subscription_id = var.subscription_id

  # Register the resource providers the shared resources depend on.
  resource_provider_registrations = "none"
  resource_providers_to_register = [
    "Microsoft.Storage",
    "Microsoft.KeyVault",
    "Microsoft.ContainerRegistry",
    "Microsoft.DocumentDB",
  ]

  features {
    key_vault {
      # Lets `terraform destroy` + re-apply work cleanly during MVP iteration.
      purge_soft_delete_on_destroy = true
    }
    resource_group {
      # Safety net: refuse to delete a resource group that still has resources
      # Terraform doesn't know about (e.g., created by hand).
      prevent_deletion_if_contains_resources = true
    }
  }
}
