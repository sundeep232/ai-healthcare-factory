variable "name" {
  description = "Logical name; sanitized and combined with the suffix to form the Azure name."
  type        = string
}

variable "suffix" {
  description = "Short unique suffix (local.suffix)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,8}$", var.suffix))
    error_message = "suffix must be 3-8 lowercase letters or digits."
  }
}

variable "resource_group_name" {
  description = "Resource group to create the server in (module.<rg>.name)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "sku" {
  description = "Server SKU, e.g. B_Standard_B1ms or B_Standard_B2s."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "storage_mb" {
  description = "Storage size in MB (minimum 32768)."
  type        = number
  default     = 32768

  validation {
    condition     = var.storage_mb >= 32768
    error_message = "storage_mb must be at least 32768."
  }
}

variable "pg_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "database_name" {
  description = "Name of the database to create on the server."
  type        = string
  default     = "appdb"
}

variable "admin_login" {
  description = "Administrator login name."
  type        = string
  default     = "pgadmin"
}

variable "key_vault_id" {
  description = "Key Vault ID (module.<kv>.id). Used only when store_admin_password is true."
  type        = string
  default     = null
}

variable "store_admin_password" {
  description = "Store the generated admin password in Key Vault as secret 'pg-admin-password'. Requires key_vault_id. Must be a literal true/false, never derived from another module's output."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
