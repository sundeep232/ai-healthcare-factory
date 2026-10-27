resource "azurerm_static_web_app" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"

  app_settings = {
    API_BASE_URL = var.api_base_url
  }

  # Sign-in settings are applied outside this resource so a later apply does not remove them.
  lifecycle {
    ignore_changes = [app_settings]
  }

  tags = var.tags
}
