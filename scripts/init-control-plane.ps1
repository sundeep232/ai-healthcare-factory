<#
.SYNOPSIS
  Points the control-plane stack at the bootstrap state storage account.

.DESCRIPTION
  Reads bootstrap outputs, writes control-plane/backend.hcl, and runs
  `terraform init`. Does not apply. Run migrate-bootstrap-state.ps1 first so
  bootstrap itself is healthy, then copy control-plane/terraform.tfvars.example
  and apply.

.EXAMPLE
  .\scripts\init-control-plane.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root       = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bootstrap  = Join-Path $root 'bootstrap'
$control    = Join-Path $root 'control-plane'

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

Push-Location $bootstrap
try {
  $raw = terraform output -json
  if ($LASTEXITCODE -ne 0) {
    throw "terraform output failed. Apply and migrate bootstrap before initializing the control plane."
  }
}
finally {
  Pop-Location
}

$out = $raw | ConvertFrom-Json
$backendFile = Join-Path $control 'backend.hcl'

Write-BackendHcl `
  -Path $backendFile `
  -ResourceGroup $out.tfstate_resource_group_name.value `
  -StorageAccount $out.tfstate_storage_account_name.value `
  -Container $out.tfstate_container_name.value `
  -UseAzureAd ([bool]$out.use_azuread_auth.value)

Write-Host "Wrote $backendFile"

Push-Location $control
try {
  terraform init -reconfigure -backend-config="$backendFile"
  if ($LASTEXITCODE -ne 0) {
    throw "terraform init failed. If this is 403, wait for the Storage Blob Data Contributor role to propagate and run this script again."
  }
}
finally {
  Pop-Location
}

Write-Host "Control-plane backend is ready. Next: copy terraform.tfvars.example to terraform.tfvars, then terraform apply in control-plane/."
