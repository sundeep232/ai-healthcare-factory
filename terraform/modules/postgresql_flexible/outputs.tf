output "id" {
  description = "Server ID."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "name" {
  description = "Server name."
  value       = azurerm_postgresql_flexible_server.this.name
}

output "fqdn" {
  description = "Server hostname."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "database_name" {
  description = "Database created on the server."
  value       = azurerm_postgresql_flexible_server_database.this.name
}

output "admin_login" {
  description = "Administrator login name."
  value       = azurerm_postgresql_flexible_server.this.administrator_login
}

output "admin_password" {
  description = "Generated administrator password. Sensitive: never surface this in root outputs."
  value       = random_password.admin.result
  sensitive   = true
}
