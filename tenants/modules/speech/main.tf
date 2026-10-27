resource "azurerm_cognitive_account" "this" {
  name                  = "speech-${var.slug}"
  location              = var.location
  resource_group_name   = var.resource_group_name
  kind                  = "SpeechServices"
  sku_name              = "S0"
  custom_subdomain_name = "speech-${var.slug}"
  tags                  = var.tags
}
