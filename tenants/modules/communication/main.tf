resource "azurerm_communication_service" "this" {
  name                = "acs-${var.slug}"
  resource_group_name = var.resource_group_name
  data_location       = "United States"
  tags                = var.tags
}
