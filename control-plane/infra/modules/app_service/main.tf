resource "azurerm_service_plan" "this" {
  name                = var.plan_name
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = var.tags
}

resource "azurerm_linux_web_app" "this" {
  name                = var.app_name
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.this.id
  https_only          = true
  tags                = var.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on  = true
    ftps_state = "Disabled"

    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING      = var.app_insights_connection_string
    ApplicationInsightsAgent_EXTENSION_VERSION = "~3"
    SQL_SERVER                                 = var.sql_server_fqdn
    SQL_DATABASE                               = var.sql_database_name
    SQL_ADMIN_LOGIN                            = var.sql_admin_login
    SQL_ADMIN_PASSWORD                         = "@Microsoft.KeyVault(SecretUri=${var.sql_password_secret_id})"
  }

  # Sign-in, GitHub Actions, Oryx, and the gunicorn command are set on the live app.
  lifecycle {
    ignore_changes = [
      app_settings,
      site_config[0].app_command_line,
    ]
  }
}
