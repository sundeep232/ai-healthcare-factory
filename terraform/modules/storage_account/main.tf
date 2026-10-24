locals {
  base  = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  alnum = replace(local.base, "-", "")
  # Name limit is 24, letters+digits only: "st" + short + suffix.
  short = substr(local.alnum, 0, min(length(local.alnum), 22 - length(var.suffix)))
}

resource "azurerm_storage_account" "this" {
  name                = "st${local.short}${var.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false

  tags = var.tags
}

resource "azurerm_storage_container" "this" {
  for_each = toset(var.containers)

  name                  = each.value
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}
