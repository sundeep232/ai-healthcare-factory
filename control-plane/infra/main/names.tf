resource "random_string" "suffix" {
  length  = 4
  upper   = false
  special = false
  numeric = true
}

resource "random_password" "sql_admin" {
  length           = 32
  special          = true
  override_special = "!#$%*-_=+?"
}

locals {
  suffix          = random_string.suffix.result
  sql_admin_login = "sqladmin"

  app_service_plan_name      = "asp-controlplane-ahf"
  web_app_name               = "app-cpahf-${local.suffix}"
  static_web_app_name        = "swa-cpahf-${local.suffix}"
  sql_server_name            = "sql-cpahf-${local.suffix}"
  sql_database_name          = "sqldb-controlplane"
  key_vault_name             = "kv-cpahf-${local.suffix}"
  log_analytics_name         = "log-controlplane-ahf"
  application_insights_name  = "appi-controlplane-ahf"
}
