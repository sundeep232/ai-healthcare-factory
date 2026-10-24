locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  # Name limit is 63; keep room for "log-" and "-<suffix>".
  short = trim(substr(local.base, 0, min(length(local.base), 63 - 5 - length(var.suffix))), "-")
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.short}-${var.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = var.sku
  retention_in_days   = var.retention_in_days
  tags                = var.tags
}
