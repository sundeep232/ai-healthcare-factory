data "azurerm_client_config" "current" {}

# Globally unique suffix. Storage account names cannot be reused after deletion
# until Azure releases them, and they have no resource-group qualifier.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

locals {
  # The deployer is included only for Entra auth. toset drops duplicates.
  state_principal_ids = var.use_azuread_auth ? toset(concat(
    [data.azurerm_client_config.current.object_id],
    var.additional_state_principal_ids
  )) : toset([])
}

resource "azurerm_resource_group" "tfstate" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

resource "azurerm_storage_account" "tfstate" {
  name                = local.storage_account_name
  resource_group_name = azurerm_resource_group.tfstate.name
  location            = azurerm_resource_group.tfstate.location

  account_tier             = "Standard"
  account_replication_type = var.replication_type
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = true
  shared_access_key_enabled       = !var.use_azuread_auth
  default_to_oauth_authentication = var.use_azuread_auth

  # State stays in this tenant. Infrastructure encryption cannot be turned off later.
  cross_tenant_replication_enabled  = false
  infrastructure_encryption_enabled = true

  blob_properties {
    versioning_enabled  = true
    change_feed_enabled = true

    delete_retention_policy {
      days = 30
    }

    container_delete_retention_policy {
      days = 30
    }
  }

  tags = local.tags

  lifecycle {
    precondition {
      condition     = !var.use_azuread_auth || length(local.state_principal_ids) > 0
      error_message = "use_azuread_auth requires a deployer principal or additional_state_principal_ids."
    }
  }
}

resource "azurerm_storage_container" "tfstate" {
  name                  = var.tfstate_container_name
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}

# Data-plane role. Management-plane Contributor cannot read or write state blobs
# once shared keys are disabled.
resource "azurerm_role_assignment" "state_blob_data_contributor" {
  for_each = local.state_principal_ids

  scope                = azurerm_storage_account.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
}
