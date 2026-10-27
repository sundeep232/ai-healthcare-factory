variable "subscription_id" {
  description = "Azure subscription that hosts platform state and the control plane."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "location" {
  description = "Azure region for the state resource group and storage account."
  type        = string
  default     = "centralus"
}

variable "name_prefix" {
  description = "Short lowercase prefix used in resource names. Letters and digits only."
  type        = string
  default     = "ahf"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.name_prefix))
    error_message = "name_prefix must be 2-8 lowercase letters or digits."
  }
}

variable "resource_group_name" {
  description = "Resource group for the state storage account. Defaults to rg-<name_prefix>-tfstate."
  type        = string
  default     = null

  validation {
    condition     = var.resource_group_name == null || can(regex("^rg-[a-z0-9-]{1,60}$", var.resource_group_name))
    error_message = "resource_group_name must match rg-[a-z0-9-] and be at most 63 characters."
  }
}

variable "tfstate_container_name" {
  description = "Blob container for every stack's state file."
  type        = string
  default     = "tfstate"

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$", var.tfstate_container_name))
    error_message = "tfstate_container_name must be a valid blob container name."
  }
}

variable "replication_type" {
  description = "Storage replication for the state account. Use LRS if the region has no availability zones."
  type        = string
  default     = "ZRS"

  validation {
    condition     = contains(["LRS", "ZRS", "GRS", "RAGRS", "GZRS"], var.replication_type)
    error_message = "replication_type must be LRS, ZRS, GRS, RAGRS, or GZRS."
  }
}

variable "use_azuread_auth" {
  description = "Store state with Entra ID (shared keys off). The apply identity needs permission to create role assignments (Owner or User Access Administrator)."
  type        = bool
  default     = true
}

variable "additional_state_principal_ids" {
  description = "Extra Entra object IDs that may read and write state. Use this for a CI service principal."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for id in var.additional_state_principal_ids :
      can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", id))
    ])
    error_message = "Each additional principal id must be a GUID."
  }
}

variable "tags" {
  description = "Extra tags merged onto every bootstrap resource. project, managed_by, and layer are always set."
  type        = map(string)
  default     = {}
}
