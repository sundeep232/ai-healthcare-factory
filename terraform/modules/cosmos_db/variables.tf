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
  description = "Resource group to create the account in (module.<rg>.name)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "database_name" {
  description = "SQL (NoSQL API) database name."
  type        = string
  default     = "appdb"
}

variable "containers" {
  description = "Container names to create in the database."
  type        = list(string)
  default     = []
}

variable "partition_key_path" {
  description = "Partition key path applied to every container."
  type        = string
  default     = "/id"
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
