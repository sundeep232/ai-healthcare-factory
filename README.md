# AI Healthcare Factory — platform foundation

Terraform layout for the Azure control plane. Two root modules, applied in order:

1. **bootstrap** creates a resource group and a storage account that hold Terraform state.
2. **control-plane** stores its state in that account and creates the shared resource group that later control-plane resources are deployed into.

State storage stays in its own resource group so tearing down the control plane cannot delete the state that describes it.

```
bootstrap/                         local apply, then remote state
  rg-<prefix>-tfstate
    st<prefix>tf<suffix>           (private container "tfstate")
      bootstrap.tfstate
      control-plane.tfstate
      <future-stack>.tfstate

control-plane/                     remote state from the first apply
  rg-<prefix>-shared               landing zone for control-plane resources
```

Default prefix is `ahf`. The bootstrap stack defaults to `centralus`. Names are overridable.

## Layout

```
bootstrap/                 state resource group, storage account, and container
scripts/                   wire remote state after bootstrap
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

Shared services (identity, Key Vault, registry, monitoring, orchestrator runtime) belong in `control-plane/` so they share this resource group and this state file.

## Prerequisites

- Terraform >= 1.6
- Azure CLI, logged in (`az login`) to the target subscription
- Permission to create resource groups and storage accounts
- For the default Entra ID state auth: permission to assign roles (Owner or User Access Administrator). With only Contributor, set `use_azuread_auth = false` in `bootstrap/terraform.tfvars` (shared keys stay on)

## Apply

```powershell
az login
az account set --subscription "<subscription-id>"

Copy-Item bootstrap\terraform.tfvars.example bootstrap\terraform.tfvars
# Set subscription_id in bootstrap\terraform.tfvars

# The backend block cannot be active until the storage account exists.
# -NewName must be a file name, not a path (PowerShell rejects the path form).
Rename-Item -Path bootstrap\backend.tf -NewName backend.tf.disabled
terraform -chdir=bootstrap init -reconfigure
terraform -chdir=bootstrap apply
Rename-Item -Path bootstrap\backend.tf.disabled -NewName backend.tf

.\scripts\migrate-bootstrap-state.ps1

Copy-Item control-plane\terraform.tfvars.example control-plane\terraform.tfvars
# Set the same subscription_id

.\scripts\init-control-plane.ps1
terraform -chdir=control-plane apply
```

`migrate-bootstrap-state.ps1` copies the local bootstrap state to blob `bootstrap.tfstate` and writes `bootstrap/backend.hcl`. `init-control-plane.ps1` writes `control-plane/backend.hcl` and runs `terraform init`. Both `backend.hcl` files and `terraform.tfvars` are git-ignored.

`terraform init -backend=false` only skips backend setup so `terraform validate` can run in CI. `plan` and `apply` need a real init.

If init returns 403 right after bootstrap, the Storage Blob Data Contributor assignment is still propagating. Wait a minute and rerun the script.

Day-to-day changes use a normal init (the backend block and `backend.hcl` are already in place):

```powershell
terraform -chdir=bootstrap plan
terraform -chdir=control-plane plan
```

## State account

The state storage account is created with:

- TLS 1.2 only, HTTPS only, no public blob access
- Shared keys disabled and `use_azuread_auth` on the backend (default)
- Infrastructure encryption, zone-redundant replication, no cross-tenant replication
- Blob versioning, change feed, and 30-day soft delete on blobs and the container

The identity that runs bootstrap is granted Storage Blob Data Contributor on the account. Pass CI object IDs in `additional_state_principal_ids`.

## What this does not create

No Key Vault, registry, network, or application resources yet. Those are added in `control-plane/` (or a follow-on stack) into `rg-<prefix>-shared`.
