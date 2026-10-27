module "app_service" {
  source = "../modules/app_service"

  plan_name                       = local.app_service_plan_name
  app_name                        = local.web_app_name
  resource_group_name             = module.resource_group.name
  location                        = module.resource_group.location
  app_insights_connection_string  = module.monitoring.application_insights_connection_string
  sql_server_fqdn                 = module.sql.server_fqdn
  sql_database_name               = module.sql.database_name
  sql_admin_login                 = local.sql_admin_login
  sql_password_secret_id          = module.key_vault.sql_admin_password_secret_id
  tags                            = local.tags
}

resource "azurerm_role_assignment" "api_key_vault_secrets_user" {
  scope                = module.key_vault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.app_service.principal_id
}
