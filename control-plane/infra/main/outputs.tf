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

output "api_hostname" {
  description = "FastAPI Demo Factory API hostname."
  value       = module.app_service.hostname
}

output "portal_hostname" {
  description = "React portal hostname."
  value       = module.static_web_app.default_host_name
}

output "sql_server_fqdn" {
  description = "Azure SQL server host name."
  value       = module.sql.server_fqdn
}

output "sql_database_name" {
  description = "Azure SQL database that holds control-plane and tenant tables."
  value       = module.sql.database_name
}

output "key_vault_name" {
  description = "Key Vault that stores the SQL administrator password."
  value       = module.key_vault.name
}

output "application_insights_name" {
  description = "Application Insights component for the API."
  value       = module.monitoring.application_insights_name
}
