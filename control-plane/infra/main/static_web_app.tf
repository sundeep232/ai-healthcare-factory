module "static_web_app" {
  source = "../modules/static_web_app"

  name                = local.static_web_app_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  api_base_url        = "https://${module.app_service.hostname}"
  tags                = local.tags
}
