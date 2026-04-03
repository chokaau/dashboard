variable "env_short" {
  description = "Short environment name used in resource names and remote state key lookups (dev, demo, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "demo", "prod"], var.env_short)
    error_message = "env_short must be one of: dev, demo, prod."
  }
}

variable "environment" {
  description = "Full environment name for tags and display (development, demo, production)"
  type        = string

  validation {
    condition     = contains(["development", "demo", "production"], var.environment)
    error_message = "environment must be one of: development, demo, production."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-southeast-2"
}

variable "image_tag" {
  description = "Docker image tag to deploy for the BFF service"
  type        = string
  default     = "latest"
}

variable "desired_count" {
  description = "Desired ECS task count for the BFF service (0 = service exists but no tasks run)"
  type        = number
  default     = 0
}

variable "task_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 512
}

variable "use_spot" {
  description = "Use FARGATE_SPOT capacity provider to reduce cost"
  type        = bool
  default     = true
}

variable "listener_rule_priority" {
  description = "ALB listener rule priority for the BFF /api/* path rule"
  type        = number
  default     = 200
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 30
}

variable "cloudfront_origin_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the CloudFront origin secret header value. Leave empty to omit the secret from the container definition."
  type        = string
  default     = ""
}
