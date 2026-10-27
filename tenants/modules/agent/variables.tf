variable "slug" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "display_name" {
  type = string
}

variable "sql_server_fqdn" {
  type = string
}

variable "sql_database_name" {
  type = string
}

variable "sql_admin_login" {
  type = string
}

variable "sql_admin_password" {
  type      = string
  sensitive = true
}

variable "openai_endpoint" {
  type = string
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "openai_deployment" {
  type = string
}

variable "speech_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "speech_region" {
  type    = string
  default = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
