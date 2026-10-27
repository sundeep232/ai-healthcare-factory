variable "plan_name" {
  description = "App Service plan name."
  type        = string
}

variable "app_name" {
  description = "Globally unique web app name for the FastAPI Demo Factory API."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the plan and web app."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "app_insights_connection_string" {
  description = "Application Insights connection string."
  type        = string
  sensitive   = true
}

variable "sql_server_fqdn" {
  description = "SQL server host name."
  type        = string
}

variable "sql_database_name" {
  description = "SQL database name."
  type        = string
}

variable "sql_admin_login" {
  description = "SQL administrator login."
  type        = string
}

variable "sql_password_secret_id" {
  description = "Versionless Key Vault secret ID for the SQL administrator password."
  type        = string
}

variable "tags" {
  description = "Tags applied to the plan and web app."
  type        = map(string)
  default     = {}
}
