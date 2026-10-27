variable "name" {
  description = "Static Web App name for the React portal."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the Static Web App."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "api_base_url" {
  description = "HTTPS origin of the FastAPI app."
  type        = string
}

variable "tags" {
  description = "Tags applied to the Static Web App."
  type        = map(string)
  default     = {}
}
