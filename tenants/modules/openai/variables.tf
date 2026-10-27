variable "slug" {
  description = "Azure-safe demo name."
  type        = string
}

variable "resource_group_name" {
  description = "Demo resource group."
  type        = string
}

variable "location" {
  description = "Region for Azure OpenAI. Central US does not host this service."
  type        = string
  default     = "eastus"
}

variable "model_name" {
  description = "Chat model deployed for this demo."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_version" {
  description = "Model version deployed for this demo. gpt-4o-mini 2024-07-18 is closed to new deployments."
  type        = string
  default     = "2025-08-07"
}

variable "capacity" {
  description = "Thousands of tokens per minute for the chat deployment."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Tags applied to the Azure OpenAI account."
  type        = map(string)
  default     = {}
}
