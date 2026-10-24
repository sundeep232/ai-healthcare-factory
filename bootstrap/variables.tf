variable "subscription_id" {
  description = "Azure subscription ID to deploy the shared resources into."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a valid GUID."
  }
}

variable "location" {
  description = "Azure region for all shared resources."
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Name of the shared resource group (matches TFSTATE_RESOURCE_GROUP in .env)."
  type        = string
  default     = "rg-factory-shared"
}

variable "name_prefix" {
  description = "Short lowercase prefix used in resource names (letters/digits only, <= 10 chars)."
  type        = string
  default     = "factory"

  validation {
    condition     = can(regex("^[a-z0-9]{1,10}$", var.name_prefix))
    error_message = "name_prefix must be 1-10 lowercase letters or digits."
  }
}

variable "tfstate_container_name" {
  description = "Blob container that stores per-instance Terraform state (matches TFSTATE_CONTAINER in .env)."
  type        = string
  default     = "tfstate"
}

variable "cosmos_database_name" {
  description = "Cosmos DB database holding blueprint, run, and manifest metadata."
  type        = string
  default     = "factory"
}

variable "tags" {
  description = "Tags applied to every shared resource."
  type        = map(string)
  default = {
    project     = "ai-healthcare-factory"
    environment = "shared"
    managed_by  = "terraform"
    scope       = "bootstrap"
  }
}
