data "azurerm_client_config" "current" {}

locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  # Name limit is 24: "kv-" + short + "-" + suffix.
  short = trim(substr(local.base, 0, min(length(local.base), 20 - length(var.suffix))), "-")
}

resource "azurerm_key_vault" "this" {
  name                = "kv-${local.short}-${var.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  # Demo environments are torn down often; keep purge protection off.
  purge_protection_enabled = false

  tags = var.tags
}

# The identity running Terraform needs data-plane rights to write secrets.
resource "azurerm_role_assignment" "deployer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}
