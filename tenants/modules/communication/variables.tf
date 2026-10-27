variable "slug" {
  description = "Azure-safe demo name."
  type        = string
}

variable "resource_group_name" {
  description = "Demo resource group."
  type        = string
}

variable "tags" {
  description = "Tags applied to Communication Services."
  type        = map(string)
  default     = {}
}
