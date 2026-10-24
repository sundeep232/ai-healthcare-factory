locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.base}-${var.suffix}"
  location = var.location
  tags     = var.tags
}
