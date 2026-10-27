locals {
  safe_name = trimspace(replace(replace(replace(replace(replace(replace(var.display_name, "&", ""), "%", ""), "<", ""), ">", ""), "\\", ""), "?", ""))
  tags = {
    project        = "ai-healthcare-factory"
    layer          = "tenant"
    managed_by     = "terraform"
    demo           = var.slug
    display_name   = length(local.safe_name) > 0 ? substr(local.safe_name, 0, 128) : var.slug
    environment_id = var.environment_id
  }
  selected = toset(var.resources)
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.slug}-ahf"
  location = var.location
  tags     = local.tags
}

module "sql" {
  count  = contains(local.selected, "sql") ? 1 : 0
  source = "../modules/sql"

  slug                = var.slug
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = local.tags
}

module "portal" {
  count  = contains(local.selected, "portal") ? 1 : 0
  source = "../modules/portal"

  slug                = var.slug
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = local.tags
}

module "openai" {
  count  = contains(local.selected, "openai") ? 1 : 0
  source = "../modules/openai"

  slug                = var.slug
  resource_group_name = azurerm_resource_group.this.name
  location            = var.openai_location
  tags                = local.tags
}

module "speech" {
  count  = contains(local.selected, "speech") ? 1 : 0
  source = "../modules/speech"

  slug                = var.slug
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = local.tags
}

module "communication" {
  count  = contains(local.selected, "communication") ? 1 : 0
  source = "../modules/communication"

  slug                = var.slug
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}
