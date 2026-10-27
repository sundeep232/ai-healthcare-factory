# Resources used to live in modules/. These blocks keep the existing Azure
# objects on the next plan instead of destroying and recreating them.
moved {
  from = module.state_resource_group.azurerm_resource_group.this
  to   = azurerm_resource_group.tfstate
}

moved {
  from = module.tfstate.azurerm_storage_account.this
  to   = azurerm_storage_account.tfstate
}

moved {
  from = module.tfstate.azurerm_storage_container.this
  to   = azurerm_storage_container.tfstate
}

moved {
  from = module.tfstate.azurerm_role_assignment.state_blob_data_contributor
  to   = azurerm_role_assignment.state_blob_data_contributor
}
