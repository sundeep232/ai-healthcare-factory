resource "random_password" "sql" {
  length           = 32
  special          = true
  override_special = "!#%*-_"
}

locals {
  safe_name = trimspace(replace(replace(replace(replace(replace(replace(var.display_name, "&", ""), "%", ""), "<", ""), ">", ""), "\\", ""), "?", ""))
  tags = {
    project        = "ai-healthcare-factory"
    layer          = "tenant"
    managed_by     = "terraform"
    demo           = var.slug
    display_name   = length(local.safe_name) > 0 ? substr(local.safe_name, 0, 128) : var.slug
    environment_id = var.environment_id
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.slug}-ahf"
  location = var.location
  tags     = local.tags
}

resource "azurerm_mssql_server" "this" {
  name                = "sql-${var.slug}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  version             = "12.0"

  administrator_login          = "sqladmin"
  administrator_login_password = random_password.sql.result
  minimum_tls_version          = "1.2"

  tags = local.tags
}

resource "azurerm_mssql_database" "this" {
  name      = "sqldb-tenant"
  server_id = azurerm_mssql_server.this.id

  sku_name                    = "GP_S_Gen5_2"
  min_capacity                = 0.5
  auto_pause_delay_in_minutes = 60
  max_size_gb                 = 32

  tags = local.tags
}

resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_static_web_app" "portal" {
  name                = "swa-${var.slug}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}
