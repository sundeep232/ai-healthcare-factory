module "rg" {
  source = "../../modules/resource_group"

  name     = var.instance_slug
  suffix   = local.suffix
  location = var.location
  tags     = local.tags
}

module "logs" {
  source = "../../modules/log_analytics"

  name                = "${var.instance_slug}-logs"
  suffix              = local.suffix
  resource_group_name = module.rg.name
  location            = var.location
  retention_in_days   = 30
  tags                = local.tags
}

module "kv" {
  source = "../../modules/key_vault"

  name                = var.instance_slug
  suffix              = local.suffix
  resource_group_name = module.rg.name
  location            = var.location
  tags                = local.tags
}

module "db" {
  source = "../../modules/postgresql_flexible"

  name                 = "${var.instance_slug}-db"
  suffix               = local.suffix
  resource_group_name  = module.rg.name
  location             = var.location
  sku                  = "B_Standard_B1ms"
  storage_mb           = 32768
  pg_version           = "16"
  database_name        = "claims"
  key_vault_id         = module.kv.id
  store_admin_password = true
  tags                 = local.tags
}

module "api" {
  source = "../../modules/container_app"

  name                       = "${var.instance_slug}-api"
  suffix                     = local.suffix
  resource_group_name        = module.rg.name
  location                   = var.location
  log_analytics_workspace_id = module.logs.id
  cpu                        = 0.5
  memory                     = "1Gi"
  min_replicas               = 0
  max_replicas               = 2

  # Non-secret settings only. The app reads the DB password from Key Vault at runtime.
  env = {
    DB_HOST        = module.db.fqdn
    DB_NAME        = module.db.database_name
    DB_USER        = module.db.admin_login
    KEY_VAULT_NAME = module.kv.name
  }

  tags = local.tags
}

module "web" {
  source = "../../modules/static_web_app"

  name                = "${var.instance_slug}-web"
  suffix              = local.suffix
  resource_group_name = module.rg.name
  location            = var.location
  sku                 = "Free"
  tags                = local.tags
}
