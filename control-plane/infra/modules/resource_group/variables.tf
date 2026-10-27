variable "name" {
  description = "Resource group name."
  type        = string

  validation {
    condition     = can(regex("^rg-[a-z0-9-]{1,60}$", var.name))
    error_message = "name must match rg-[a-z0-9-] and be at most 63 characters."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "tags" {
  description = "Tags applied to the resource group."
  type        = map(string)
  default     = {}
}
