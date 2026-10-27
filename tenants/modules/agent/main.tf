resource "azurerm_service_plan" "this" {
  name                = "asp-${var.slug}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = var.tags
}

resource "azurerm_linux_web_app" "this" {
  name                = "app-${var.slug}"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.this.id
  https_only          = true
  tags                = var.tags

  site_config {
    always_on        = true
    ftps_state       = "Disabled"
    app_command_line = "gunicorn -w 2 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:8000 --timeout 120"

    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD               = "true"
    WEBSITES_PORT                   = "8000"
    DEMO_NAME                       = var.display_name
    SQL_SERVER                      = var.sql_server_fqdn
    SQL_DATABASE                    = var.sql_database_name
    SQL_ADMIN_LOGIN                 = var.sql_admin_login
    SQL_ADMIN_PASSWORD              = var.sql_admin_password
    OPENAI_ENDPOINT                 = var.openai_endpoint
    OPENAI_API_KEY                  = var.openai_api_key
    OPENAI_DEPLOYMENT               = var.openai_deployment
    SPEECH_KEY                      = var.speech_key
    SPEECH_REGION                   = var.speech_region
  }
}
