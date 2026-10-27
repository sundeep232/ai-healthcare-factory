output "endpoint" {
  value = azurerm_cognitive_account.this.endpoint
}

output "account_name" {
  value = azurerm_cognitive_account.this.name
}

output "primary_access_key" {
  value     = azurerm_cognitive_account.this.primary_access_key
  sensitive = true
}

output "deployment_name" {
  value = azurerm_cognitive_deployment.chat.name
}
