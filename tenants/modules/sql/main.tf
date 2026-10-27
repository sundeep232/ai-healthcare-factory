resource "random_password" "sql" {
  length           = 32
  special          = true
  override_special = "!#%*-_"
}

resource "azurerm_mssql_server" "this" {
  name                = "sql-${var.slug}"
  resource_group_name = var.resource_group_name
  location            = var.location
  version             = "12.0"

  administrator_login          = "sqladmin"
  administrator_login_password = random_password.sql.result
  minimum_tls_version          = "1.2"

  tags = var.tags
}

resource "azurerm_mssql_database" "this" {
  name      = "sqldb-tenant"
  server_id = azurerm_mssql_server.this.id

  sku_name                    = "GP_S_Gen5_2"
  min_capacity                = 0.5
  auto_pause_delay_in_minutes = 60
  max_size_gb                 = 32

  tags = var.tags
}

resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
