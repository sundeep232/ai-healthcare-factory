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
  description = "Resource group to create the workspace in (module.<rg>.name)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "sku" {
  description = "Workspace SKU."
  type        = string
  default     = "PerGB2018"
}

variable "retention_in_days" {
  description = "Log retention in days (30-730)."
  type        = number
  default     = 30

  validation {
    condition     = var.retention_in_days >= 30 && var.retention_in_days <= 730
    error_message = "retention_in_days must be between 30 and 730."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
