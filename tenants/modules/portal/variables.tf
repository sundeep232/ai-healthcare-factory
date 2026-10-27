variable "slug" {
  description = "Azure-safe demo name."
  type        = string
}

variable "resource_group_name" {
  description = "Demo resource group."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "tags" {
  description = "Tags applied to the portal site."
  type        = map(string)
  default     = {}
}
