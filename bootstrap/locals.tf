locals {
  resource_group_name  = coalesce(var.resource_group_name, "rg-${var.name_prefix}-tfstate")
  storage_account_name = "st${var.name_prefix}tf${random_string.suffix.result}"

  tags = merge(
    {
      environment = "shared"
      purpose     = "terraform-state"
    },
    var.tags,
    {
      project    = "ai-healthcare-factory"
      managed_by = "terraform"
      layer      = "bootstrap"
    }
  )
}
