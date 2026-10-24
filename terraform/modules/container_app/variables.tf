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
  description = "Resource group to create the app in (module.<rg>.name)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Optional Log Analytics workspace ID (module.<logs>.id) for container logs."
  type        = string
  default     = null
}

variable "image" {
  description = "Container image. The default is Microsoft's quickstart placeholder."
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "target_port" {
  description = "Port the container listens on."
  type        = number
  default     = 80
}

variable "cpu" {
  description = "vCPU (must pair with a valid memory size, e.g. 0.5 with 1Gi)."
  type        = number
  default     = 0.5
}

variable "memory" {
  description = "Memory, e.g. 1Gi."
  type        = string
  default     = "1Gi"
}

variable "min_replicas" {
  description = "Minimum replicas (0 allows scale-to-zero)."
  type        = number
  default     = 0
}

variable "max_replicas" {
  description = "Maximum replicas."
  type        = number
  default     = 2
}

variable "env" {
  description = "Plain (non-secret) environment variables. Never put secrets here."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
