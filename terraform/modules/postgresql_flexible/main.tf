locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  # Name limit is 63: "psql-" + short + "-" + suffix.
  short = trim(substr(local.base, 0, min(length(local.base), 63 - 6 - length(var.suffix))), "-")
}

# Generated here and never exposed except as a sensitive output / Key Vault secret.
resource "random_password" "admin" {
  length           = 24
  special          = true
  override_special = "!#%*-_"
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                = "psql-${local.short}-${var.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name

  version    = var.pg_version
  sku_name   = var.sku
  storage_mb = var.storage_mb

  administrator_login    = var.admin_login
  administrator_password = random_password.admin.result

  backup_retention_days         = 7
  public_network_access_enabled = true

  tags = var.tags

  lifecycle {
    # Azure assigns the zone; changing it later would force replacement.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 - 0.0.0.0 is Azure's convention for "allow Azure services". Demo-grade:
# tighten with private networking before using real data.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Optionally store the generated admin password in Key Vault.
# `count` must not depend on var.key_vault_id: that ID is usually unknown until
# apply (it comes from another module), and Terraform can't plan an unknown count.
resource "azurerm_key_vault_secret" "admin_password" {
  count = var.store_admin_password ? 1 : 0

  name         = "pg-admin-password"
  value        = random_password.admin.result
  key_vault_id = var.key_vault_id

  lifecycle {
    precondition {
      condition     = var.key_vault_id != null
      error_message = "store_admin_password = true requires key_vault_id."
    }
  }
}
