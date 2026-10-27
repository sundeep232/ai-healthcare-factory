output "server_fqdn" {
  value = azurerm_mssql_server.this.fully_qualified_domain_name
}

output "admin_login" {
  value = "sqladmin"
}

output "admin_password" {
  value     = random_password.sql.result
  sensitive = true
}

output "database_name" {
  value = azurerm_mssql_database.this.name
}
