output "id" {
  description = "Static Web App ID."
  value       = azurerm_static_web_app.this.id
}

output "name" {
  description = "Static Web App name."
  value       = azurerm_static_web_app.this.name
}

output "url" {
  description = "Public HTTPS URL of the site."
  value       = "https://${azurerm_static_web_app.this.default_host_name}"
}
