output "tfstate_resource_group_name" {
  description = "Resource group that holds the state storage account."
  value       = azurerm_resource_group.tfstate.name
}

output "tfstate_storage_account_name" {
  description = "Storage account for remote Terraform state."
  value       = azurerm_storage_account.tfstate.name
}

output "tfstate_storage_account_id" {
  description = "Resource ID of the state storage account."
  value       = azurerm_storage_account.tfstate.id
}

output "tfstate_container_name" {
  description = "Blob container for state files. One container, one blob key per stack."
  value       = azurerm_storage_container.tfstate.name
}

output "use_azuread_auth" {
  description = "Pass through to backend.hcl so every stack matches the account's auth mode."
  value       = var.use_azuread_auth
}

output "location" {
  description = "Region of the state resources."
  value       = azurerm_resource_group.tfstate.location
}
