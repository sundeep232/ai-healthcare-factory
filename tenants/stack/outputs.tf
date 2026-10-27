output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "sql_server_fqdn" {
  value = one(module.sql[*].server_fqdn)
}

output "sql_admin_login" {
  value = one(module.sql[*].admin_login)
}

output "sql_admin_password" {
  value     = one(module.sql[*].admin_password)
  sensitive = true
}

output "portal_hostname" {
  value = one(module.portal[*].default_host_name)
}

output "agent_hostname" {
  value = one(module.agent[*].default_hostname)
}

output "openai_endpoint" {
  value = one(module.openai[*].endpoint)
}

output "speech_endpoint" {
  value = one(module.speech[*].endpoint)
}

output "communication_hostname" {
  value = one(module.communication[*].hostname)
}