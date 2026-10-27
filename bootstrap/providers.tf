provider "azurerm" {
  subscription_id = var.subscription_id

  # Blob data-plane calls follow the same auth mode as the azurerm backend.
  storage_use_azuread = var.use_azuread_auth

  resource_provider_registrations = "none"
  resource_providers_to_register = [
    "Microsoft.Storage",
  ]

  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
