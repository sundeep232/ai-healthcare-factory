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
  description = "Resource group to create the app in (module.<rg>.name)."
  type        = string
}

variable "location" {
  description = "Azure region (Static Web Apps support only a few regions, e.g. eastus2, centralus, westus2)."
  type        = string
}

variable "sku" {
  description = "Free or Standard."
  type        = string
  default     = "Free"

  validation {
    condition     = contains(["Free", "Standard"], var.sku)
    error_message = "sku must be Free or Standard."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
