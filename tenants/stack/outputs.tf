output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.this.fully_qualified_domain_name
}

output "portal_hostname" {
  value = azurerm_static_web_app.portal.default_host_name
}
