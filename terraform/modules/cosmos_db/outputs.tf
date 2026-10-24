output "id" {
  description = "Cosmos DB account ID."
  value       = azurerm_cosmosdb_account.this.id
}

output "name" {
  description = "Cosmos DB account name."
  value       = azurerm_cosmosdb_account.this.name
}

output "endpoint" {
  description = "Account endpoint URL."
  value       = azurerm_cosmosdb_account.this.endpoint
}

output "database_name" {
  description = "Database name."
  value       = azurerm_cosmosdb_sql_database.this.name
}
