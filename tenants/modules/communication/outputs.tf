output "hostname" {
  value = azurerm_communication_service.this.hostname
}

output "primary_connection_string" {
  value     = azurerm_communication_service.this.primary_connection_string
  sensitive = true
}
