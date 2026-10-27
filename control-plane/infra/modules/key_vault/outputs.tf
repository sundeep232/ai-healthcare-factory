output "id" {
  description = "Key Vault resource ID."
  value       = azurerm_key_vault.this.id
}

output "name" {
  description = "Key Vault name."
  value       = azurerm_key_vault.this.name
}

output "uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.this.vault_uri
}

output "sql_admin_password_secret_id" {
  description = "Versionless secret ID the API uses for the SQL administrator password."
  value       = azurerm_key_vault_secret.sql_admin_password.versionless_id
}
