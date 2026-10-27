<#
.SYNOPSIS
  Copies bootstrap local state into the storage account it just created.

.DESCRIPTION
  Run once, after the first local `terraform apply` in bootstrap/. Restores
  backend.tf if it is still named backend.tf.disabled, writes backend.hcl from
  the state outputs, and runs `terraform init -migrate-state`.

.EXAMPLE
  .\scripts\migrate-bootstrap-state.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$bootstrap = (Resolve-Path (Join-Path $PSScriptRoot '..\bootstrap')).Path

function Get-BootstrapOutputs {
  param([string]$BootstrapDir)

  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  Push-Location $BootstrapDir
  try {
    $raw = terraform output -json 2>$null
    if ($LASTEXITCODE -eq 0 -and $raw) {
      return $raw | ConvertFrom-Json
    }
  }
  finally {
    Pop-Location
    $ErrorActionPreference = $previous
  }

  # backend.tf may already be restored, which blocks `terraform output` until
  # init. The first apply left the outputs in the local state file.
  $statePath = Join-Path $BootstrapDir 'terraform.tfstate'
  if (-not (Test-Path $statePath)) {
    throw "No bootstrap outputs. Apply bootstrap with the local backend first (backend.tf renamed aside)."
  }

  $state = Get-Content -Raw -Path $statePath | ConvertFrom-Json
  if (-not $state.outputs) {
    throw "Local bootstrap state has no outputs. Apply bootstrap before migrating."
  }
  return $state.outputs
}

function Write-BackendHcl {
  param(
    [string]$Path,
    [string]$ResourceGroup,
    [string]$StorageAccount,
    [string]$Container,
    [bool]$UseAzureAd
  )

  $auth = $UseAzureAd.ToString().ToLower()
  $content = @"
resource_group_name  = "$ResourceGroup"
storage_account_name = "$StorageAccount"
container_name       = "$Container"
use_azuread_auth     = $auth

"@
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($Path, $content, $utf8)
}

$disabledBackend = Join-Path $bootstrap 'backend.tf.disabled'
$backendTf      = Join-Path $bootstrap 'backend.tf'
if (-not (Test-Path $backendTf) -and (Test-Path $disabledBackend)) {
  Rename-Item -Path $disabledBackend -NewName 'backend.tf'
  Write-Host "Restored $backendTf"
}

$out = Get-BootstrapOutputs -BootstrapDir $bootstrap
$backendFile = Join-Path $bootstrap 'backend.hcl'

Write-BackendHcl `
  -Path $backendFile `
  -ResourceGroup $out.tfstate_resource_group_name.value `
  -StorageAccount $out.tfstate_storage_account_name.value `
  -Container $out.tfstate_container_name.value `
  -UseAzureAd ([bool]$out.use_azuread_auth.value)

Write-Host "Wrote $backendFile"

Push-Location $bootstrap
try {
  terraform init -migrate-state -force-copy -backend-config="$backendFile"
  if ($LASTEXITCODE -ne 0) {
    throw "terraform init -migrate-state failed. If this is AuthorizationFailed or 403, the Storage Blob Data Contributor assignment is still propagating; wait a minute and run this script again."
  }
}
finally {
  Pop-Location
}

Write-Host "Bootstrap state is now blob bootstrap.tfstate."
