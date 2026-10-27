variable "server_name" {
  description = "Globally unique SQL server name."
  type        = string
}

variable "database_name" {
  description = "Control-plane database name."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the SQL server."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "admin_login" {
  description = "SQL administrator login."
  type        = string
}

variable "admin_password" {
  description = "SQL administrator password."
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to the SQL server."
  type        = map(string)
  default     = {}
}
