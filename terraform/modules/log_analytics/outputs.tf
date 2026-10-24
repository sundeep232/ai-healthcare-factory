output "id" {
  description = "Workspace ID (pass as log_analytics_workspace_id to container_app)."
  value       = azurerm_log_analytics_workspace.this.id
}

output "name" {
  description = "Workspace name."
  value       = azurerm_log_analytics_workspace.this.name
}
