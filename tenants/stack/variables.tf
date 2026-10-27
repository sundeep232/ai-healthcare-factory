variable "subscription_id" {
  description = "Azure subscription. Same subscription as the control plane."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "location" {
  description = "Azure region for this demo."
  type        = string
  default     = "centralus"
}

variable "slug" {
  description = "Demo name from the portal, made safe for Azure resource names."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.slug))
    error_message = "slug must be 3-40 characters of lowercase letters, numbers, and hyphens."
  }
}

variable "environment_id" {
  description = "Control-plane environment id for this demo."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.environment_id))
    error_message = "environment_id must be a GUID."
  }
}

variable "display_name" {
  description = "Demo name typed in the portal."
  type        = string
}

variable "openai_location" {
  description = "Region for Azure OpenAI. The resource group stays in var.location."
  type        = string
  default     = "eastus"
}

variable "resources" {
  description = "Modules selected by the demo template."
  type        = list(string)
  default     = ["sql", "portal"]

  validation {
    condition = length(var.resources) == length(distinct(var.resources)) && alltrue([
      for name in var.resources : contains(["sql", "portal", "openai", "speech", "communication"], name)
    ])
    error_message = "resources must be unique names from sql, portal, openai, speech, and communication."
  }
}
