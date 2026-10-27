variable "name" {
  description = "Key Vault name. Globally unique, 3-24 characters."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]$", var.name))
    error_message = "name must be 3-24 characters, start with a letter, and end with a letter or digit."
  }
}

variable "resource_group_name" {
  description = "Resource group for the Key Vault."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant ID."
  type        = string
}

variable "deployer_object_id" {
  description = "Object ID granted Key Vault Administrator so Terraform can write secrets."
  type        = string
}

variable "sql_admin_password" {
  description = "SQL administrator password stored as a secret."
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to the Key Vault."
  type        = map(string)
  default     = {}
}
