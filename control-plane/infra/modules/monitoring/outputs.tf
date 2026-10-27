output "log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID."
  value       = azurerm_log_analytics_workspace.this.id
}

output "application_insights_connection_string" {
  description = "Connection string the API uses to send telemetry."
  value       = azurerm_application_insights.this.connection_string
  sensitive   = true
}

output "application_insights_name" {
  description = "Application Insights component name."
  value       = azurerm_application_insights.this.name
}
