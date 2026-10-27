# One state file per demo. The workflow passes key=tenants/<slug>.tfstate.
terraform {
  backend "azurerm" {}
}
