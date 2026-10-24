locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  # Name limit is 60: "swa-" + short + "-" + suffix.
  short = trim(substr(local.base, 0, min(length(local.base), 60 - 5 - length(var.suffix))), "-")
}

resource "azurerm_static_web_app" "this" {
  name                = "swa-${local.short}-${var.suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = var.sku
  sku_size            = var.sku
  tags                = var.tags
}
