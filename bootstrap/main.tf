# Shared, one-time infrastructure for the AI-Driven Healthcare Platform Factory.
#
# Creates:
#   - Resource group (rg-factory-shared)
#   - Storage account + container  -> remote Terraform state for per-instance deploys
#   - Key Vault (RBAC)             -> secrets (Claude API key, credentials)
#   - Azure Container Registry     -> images for orchestrator / demo apps
#   - Cosmos DB (serverless)       -> blueprint, run, and manifest metadata

data "azurerm_client_config" "current" {}

# Globally-unique suffix so storage / Key Vault / ACR / Cosmos names don't collide.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

locals {
  suffix = random_string.suffix.result

  # Naming rules differ per service (length, allowed characters).
  storage_account_name = "st${var.name_prefix}tf${local.suffix}"     # 3-24, lowercase+digits
  key_vault_name       = "kv-${var.name_prefix}-${local.suffix}"     # 3-24, alphanumeric + hyphen
  acr_name             = "acr${var.name_prefix}${local.suffix}"      # 5-50, alphanumeric
  cosmos_account_name  = "cosmos-${var.name_prefix}-${local.suffix}" # 3-44, lowercase+digits+hyphen

  # Containers in the Cosmos DB database: name => partition key path.
  cosmos_containers = {
    blueprints = "/id"
    runs       = "/blueprint_id"
    manifests  = "/instance_id"
  }
}

# --- Resource group ----------------------------------------------------------

resource "azurerm_resource_group" "shared" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# --- Terraform remote state --------------------------------------------------

resource "azurerm_storage_account" "tfstate" {
  name                = local.storage_account_name
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false

  # Keep shared-key access on for the MVP so `terraform init` works with simple
  # env-based auth. Tighten to Entra-only (use_azuread_auth) in a later phase.
  shared_access_key_enabled = true

  blob_properties {
    # Versioning + soft delete protect state files against accidental overwrite.
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "tfstate" {
  name                  = var.tfstate_container_name
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}

# --- Key Vault ---------------------------------------------------------------

resource "azurerm_key_vault" "shared" {
  name                = local.key_vault_name
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # RBAC instead of legacy access policies.
  rbac_authorization_enabled = true

  soft_delete_retention_days = 7
  # Off for the MVP so the vault can be fully destroyed/recreated. Turn ON for production.
  purge_protection_enabled = false

  tags = var.tags
}

# The identity running Terraform needs data-plane rights to manage secrets.
resource "azurerm_role_assignment" "deployer_key_vault_admin" {
  scope                = azurerm_key_vault.shared.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

# --- Container registry ------------------------------------------------------

resource "azurerm_container_registry" "shared" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
  sku                 = "Basic"

  # Use Entra ID / managed identity (AcrPull/AcrPush) rather than a shared admin password.
  admin_enabled = false

  tags = var.tags
}

# --- Cosmos DB (serverless, NoSQL API) ----------------------------------------

resource "azurerm_cosmosdb_account" "shared" {
  name                = local.cosmos_account_name
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  # Serverless: pay per request, ideal for spiky demo/metadata workloads.
  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.shared.location
    failover_priority = 0
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "factory" {
  name                = var.cosmos_database_name
  resource_group_name = azurerm_resource_group.shared.name
  account_name        = azurerm_cosmosdb_account.shared.name
}

resource "azurerm_cosmosdb_sql_container" "collections" {
  for_each = local.cosmos_containers

  name                = each.key
  resource_group_name = azurerm_resource_group.shared.name
  account_name        = azurerm_cosmosdb_account.shared.name
  database_name       = azurerm_cosmosdb_sql_database.factory.name
  partition_key_paths = [each.value]
}
