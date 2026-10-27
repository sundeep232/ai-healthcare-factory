resource "azurerm_static_web_app" "this" {
  name                = "swa-${var.slug}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = var.tags
}
