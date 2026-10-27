provider "azurerm" {
  subscription_id = var.subscription_id

  resource_provider_registrations = "none"
  resource_providers_to_register = [
    "Microsoft.Web",
    "Microsoft.Sql",
    "Microsoft.KeyVault",
    "Microsoft.Insights",
    "Microsoft.OperationalInsights",
  ]

  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}
