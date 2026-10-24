output "id" {
  description = "Container App ID."
  value       = azurerm_container_app.this.id
}

output "name" {
  description = "Container App name."
  value       = azurerm_container_app.this.name
}

output "url" {
  description = "Public HTTPS URL of the app."
  value       = "https://${azurerm_container_app.this.ingress[0].fqdn}"
}

output "principal_id" {
  description = "Managed identity principal ID (for role assignments)."
  value       = azurerm_container_app.this.identity[0].principal_id
}
