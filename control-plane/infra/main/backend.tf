# Same storage account and container as bootstrap/backend.hcl.
# This stack uses its own blob key so it does not overwrite bootstrap.tfstate.
#
#   terraform init -backend-config=..\..\..\bootstrap\backend.hcl
terraform {
  backend "azurerm" {
    key = "control-plane.tfstate"
  }
}
