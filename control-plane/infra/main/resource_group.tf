locals {
  tags = merge(
    {
      environment = "shared"
      purpose     = "control-plane"
    },
    var.tags,
    {
      project    = "ai-healthcare-factory"
      managed_by = "terraform"
      layer      = "control-plane"
    }
  )
}

module "resource_group" {
  source = "../modules/resource_group"

  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}
