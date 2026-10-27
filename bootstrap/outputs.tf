output "tfstate_resource_group_name" {
  description = "Resource group that holds the state storage account."
  value       = module.state_resource_group.name
}

output "tfstate_storage_account_name" {
  description = "Storage account for remote Terraform state."
  value       = module.tfstate.storage_account_name
}

output "tfstate_storage_account_id" {
  description = "Resource ID of the state storage account."
  value       = module.tfstate.storage_account_id
}

output "tfstate_container_name" {
  description = "Blob container for state files. One container, one blob key per stack."
  value       = module.tfstate.container_name
}

output "use_azuread_auth" {
  description = "Pass through to backend.hcl so every stack matches the account's auth mode."
  value       = var.use_azuread_auth
}

output "location" {
  description = "Region of the state resources."
  value       = module.state_resource_group.location
}
