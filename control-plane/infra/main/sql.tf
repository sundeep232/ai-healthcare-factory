module "sql" {
  source = "../modules/sql"

  server_name         = local.sql_server_name
  database_name       = local.sql_database_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  admin_login         = local.sql_admin_login
  admin_password      = random_password.sql_admin.result
  tags                = local.tags
}
