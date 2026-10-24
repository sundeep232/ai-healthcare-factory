output "id" {
  description = "Key Vault ID. Resolves only after the deployer's admin role exists, so it is safe to pass as key_vault_id to modules that write secrets."
  value       = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.deployer]
}

output "name" {
  description = "Key Vault name."
  value       = azurerm_key_vault.this.name
}

output "vault_uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.this.vault_uri
}
