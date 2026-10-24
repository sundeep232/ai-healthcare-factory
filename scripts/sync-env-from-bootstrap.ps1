<#
.SYNOPSIS
  Copies `terraform output` values from bootstrap/ into the project-root .env.

.DESCRIPTION
  Run after `terraform apply` in bootstrap/. Updates only the shared-resource keys
  (TFSTATE_*, KEY_VAULT_NAME, ACR_LOGIN_SERVER, COSMOS_ENDPOINT, AZURE_TENANT_ID);
  every other line in .env (including your Claude key) is left untouched.

.EXAMPLE
  .\scripts\sync-env-from-bootstrap.ps1
#>
[CmdletBinding()]
param(
  [string]$EnvFile = (Join-Path $PSScriptRoot '..\.env'),
  [string]$BootstrapDir = (Join-Path $PSScriptRoot '..\bootstrap')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $EnvFile)) {
  throw ".env not found at $EnvFile. Run: Copy-Item .env.example .env"
}

# Read outputs from Terraform state.
$raw = terraform "-chdir=$BootstrapDir" output -json
if ($LASTEXITCODE -ne 0) { throw "terraform output failed. Has 'terraform apply' completed in bootstrap/?" }
$out = $raw | ConvertFrom-Json

# terraform output name -> .env key
$map = [ordered]@{
  TFSTATE_RESOURCE_GROUP  = $out.tfstate_resource_group.value
  TFSTATE_STORAGE_ACCOUNT = $out.tfstate_storage_account.value
  TFSTATE_CONTAINER       = $out.tfstate_container.value
  KEY_VAULT_NAME          = $out.key_vault_name.value
  ACR_LOGIN_SERVER        = $out.acr_login_server.value
  COSMOS_ENDPOINT         = $out.cosmos_endpoint.value
  AZURE_TENANT_ID         = $out.azure_tenant_id.value
}

$lines = [System.Collections.Generic.List[string]](Get-Content $EnvFile)

foreach ($key in $map.Keys) {
  $newLine = "$key=$($map[$key])"
  $idx = $lines.FindIndex({ param($l) $l -match "^\s*$key\s*=" })
  if ($idx -ge 0) { $lines[$idx] = $newLine } else { $lines.Add($newLine) }
  Write-Host "  set $key" -ForegroundColor Green
}

Set-Content -Path $EnvFile -Value $lines -Encoding utf8
Write-Host "Updated $EnvFile" -ForegroundColor Cyan
