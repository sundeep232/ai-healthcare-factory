# Output names map 1:1 to the "Shared Resources" block in .env
# (see scripts/sync-env-from-bootstrap.ps1).

output "tfstate_resource_group" {
  description = "-> TFSTATE_RESOURCE_GROUP"
  value       = azurerm_resource_group.shared.name
}

output "tfstate_storage_account" {
  description = "-> TFSTATE_STORAGE_ACCOUNT"
  value       = azurerm_storage_account.tfstate.name
}

output "tfstate_container" {
  description = "-> TFSTATE_CONTAINER"
  value       = azurerm_storage_container.tfstate.name
}

output "key_vault_name" {
  description = "-> KEY_VAULT_NAME"
  value       = azurerm_key_vault.shared.name
}

output "acr_login_server" {
  description = "-> ACR_LOGIN_SERVER"
  value       = azurerm_container_registry.shared.login_server
}

output "cosmos_endpoint" {
  description = "-> COSMOS_ENDPOINT"
  value       = azurerm_cosmosdb_account.shared.endpoint
}

output "azure_tenant_id" {
  description = "-> AZURE_TENANT_ID"
  value       = data.azurerm_client_config.current.tenant_id
}
