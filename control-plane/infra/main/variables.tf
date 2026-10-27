variable "subscription_id" {
  description = "Azure subscription. Use the same subscription as bootstrap."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "location" {
  description = "Azure region for the control-plane resource group."
  type        = string
  default     = "centralus"
}

variable "resource_group_name" {
  description = "Resource group for control-plane resources."
  type        = string
  default     = "rg-controlplane-ahf"

  validation {
    condition     = can(regex("^rg-[a-z0-9-]{1,60}$", var.resource_group_name))
    error_message = "resource_group_name must match rg-[a-z0-9-] and be at most 63 characters."
  }
}

variable "tags" {
  description = "Extra tags merged onto the resource group. project, managed_by, and layer are always set."
  type        = map(string)
  default     = {}
}
