locals {
  base = trim(lower(replace(var.name, "/[^a-zA-Z0-9]+/", "-")), "-")
  # Container App name limit is 32: "ca-" + short + "-" + suffix.
  short = trim(substr(local.base, 0, min(length(local.base), 32 - 4 - length(var.suffix))), "-")
}

resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${local.short}-${var.suffix}"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = var.log_analytics_workspace_id
  tags                       = var.tags
}

resource "azurerm_container_app" "this" {
  name                         = "ca-${local.short}-${var.suffix}"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  tags                         = var.tags

  # Lets the app read secrets from Key Vault at runtime (grant roles separately).
  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = var.target_port

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "app"
      image  = var.image
      cpu    = var.cpu
      memory = var.memory

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}
