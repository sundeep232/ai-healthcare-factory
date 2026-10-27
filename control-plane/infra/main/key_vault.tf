data "azurerm_client_config" "current" {}

module "key_vault" {
  source = "../modules/key_vault"

  name                = local.key_vault_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  deployer_object_id  = data.azurerm_client_config.current.object_id
  sql_admin_password  = random_password.sql_admin.result
  tags                = local.tags
}
