output "plan_id" {
  description = "App Service plan resource ID."
  value       = azurerm_service_plan.this.id
}

output "app_id" {
  description = "Web app resource ID."
  value       = azurerm_linux_web_app.this.id
}

output "hostname" {
  description = "Default hostname of the FastAPI app."
  value       = azurerm_linux_web_app.this.default_hostname
}

output "principal_id" {
  description = "System-assigned identity of the web app."
  value       = azurerm_linux_web_app.this.identity[0].principal_id
}
