output "server_id" {
  description = "SQL server resource ID."
  value       = azurerm_mssql_server.this.id
}

output "server_name" {
  description = "SQL server name."
  value       = azurerm_mssql_server.this.name
}

output "server_fqdn" {
  description = "SQL server fully qualified domain name."
  value       = azurerm_mssql_server.this.fully_qualified_domain_name
}

output "database_name" {
  description = "Control-plane database name."
  value       = azurerm_mssql_database.this.name
}
