output "resource_group_name" {
  description = "Control-plane resource group."
  value       = module.resource_group.name
}

output "resource_group_id" {
  description = "Resource ID of the control-plane resource group."
  value       = module.resource_group.id
}

output "location" {
  description = "Region of the control-plane resource group."
  value       = module.resource_group.location
}
