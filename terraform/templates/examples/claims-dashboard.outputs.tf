output "resource_group_name" {
  description = "Resource group holding the demo."
  value       = module.rg.name
}

output "api_url" {
  description = "Public URL of the demo API."
  value       = module.api.url
}

output "web_url" {
  description = "Public URL of the demo UI."
  value       = module.web.url
}

output "database_host" {
  description = "PostgreSQL hostname."
  value       = module.db.fqdn
}

output "key_vault_name" {
  description = "Key Vault holding the instance secrets."
  value       = module.kv.name
}
