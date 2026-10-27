module "monitoring" {
  source = "../modules/monitoring"

  resource_group_name       = module.resource_group.name
  location                  = module.resource_group.location
  log_analytics_name        = local.log_analytics_name
  application_insights_name = local.application_insights_name
  tags                      = local.tags
}
