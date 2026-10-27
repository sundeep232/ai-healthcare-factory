data "azurerm_client_config" "current" {}

# Globally unique suffix. Storage account names cannot be reused after deletion
# until Azure releases them, and they have no resource-group qualifier.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

module "state_resource_group" {
  source = "../modules/resource_group"

  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

module "tfstate" {
  source = "../modules/tfstate_backend"

  storage_account_name     = local.storage_account_name
  resource_group_name      = module.state_resource_group.name
  location                 = module.state_resource_group.location
  container_name           = var.tfstate_container_name
  replication_type         = var.replication_type
  use_azuread_auth         = var.use_azuread_auth
  deployer_principal_id    = data.azurerm_client_config.current.object_id
  additional_principal_ids = var.additional_state_principal_ids
  tags                     = local.tags
}
