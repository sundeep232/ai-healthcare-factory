output "id" {
  description = "Resource group ID."
  value       = azurerm_resource_group.this.id
}

output "name" {
  description = "Resource group name (pass as resource_group_name to other modules)."
  value       = azurerm_resource_group.this.name
}

output "location" {
  description = "Resource group region."
  value       = azurerm_resource_group.this.location
}
