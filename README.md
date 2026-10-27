# AI Healthcare Factory — platform foundation

Terraform layout for the Azure control plane. Two root modules, applied in order:

1. **bootstrap** creates a resource group and a storage account that hold Terraform state.
2. **control-plane** stores its state in that account and creates the shared resource group that later control-plane resources are deployed into.

State storage stays in its own resource group so tearing down the control plane cannot delete the state that describes it.

```
bootstrap/                         state storage
  rg-ahf-tfstate
    stahftf4jqp3v                  container "tfstate"
      bootstrap.tfstate
      control-plane.tfstate

control-plane/infra/main/         control-plane resources
  rg-controlplane-ahf
```

Default region is `centralus`.

## Layout

```
bootstrap/                 state resource group, storage account, and container
control-plane/infra/main/             Terraform root (resource_group.tf)
control-plane/infra/modules/resource_group/   resource group module
```

A later stack gets its own directory and its own blob key (`network.tfstate`, `workload.tfstate`). It reads the shared group from remote state when a resource must live there:

```hcl
data "terraform_remote_state" "control_plane" {
  backend = "azurerm"

  config = {
    resource_group_name  = "<tfstate_resource_group_name>"
    storage_account_name = "<tfstate_storage_account_name>"
    container_name       = "tfstate"
    key                  = "control-plane.tfstate"
    use_azuread_auth     = true
  }
}
```

Shared services (identity, Key Vault, registry, monitoring, orchestrator runtime) belong in `control-plane/infra/main` so they share `rg-controlplane-ahf` and `control-plane.tfstate`.

## Prerequisites

- Terraform >= 1.6
- Azure CLI, logged in (`az login`) to the target subscription
- Permission to create resource groups and storage accounts
- For the default Entra ID state auth: permission to assign roles (Owner or User Access Administrator). With only Contributor, set `use_azuread_auth = false` in `bootstrap/terraform.tfvars` (shared keys stay on)

## Apply

Bootstrap is already applied. Its state blob is `bootstrap.tfstate` in the storage account recorded in `bootstrap/backend.hcl`.

Create the control-plane resource group with that same backend file and a separate state key, `control-plane.tfstate`:

```powershell
az login
Set-Location control-plane\infra\main
terraform init -backend-config=..\..\..\bootstrap\backend.hcl
terraform apply
```

`terraform.tfvars` is git-ignored. `control-plane/infra/main/terraform.tfvars` is already filled with the bootstrap subscription.

## State account

The state storage account is created with:

- TLS 1.2 only, HTTPS only, no public blob access
- Shared keys disabled and `use_azuread_auth` on the backend (default)
- Infrastructure encryption, zone-redundant replication, no cross-tenant replication
- Blob versioning, change feed, and 30-day soft delete on blobs and the container

The identity that runs bootstrap is granted Storage Blob Data Contributor on the account. Pass CI object IDs in `additional_state_principal_ids`.

## What this does not create

No Key Vault, registry, network, or application resources yet. Those are added in `control-plane/infra/main` inside `rg-controlplane-ahf`.
