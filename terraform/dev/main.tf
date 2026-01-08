# Simple Terraform config for E2E testing
# Uses local backend (no cloud resources needed)

terraform {
  required_version = ">= 1.0.0"

  # Local file backend - no cloud credentials needed
  backend "local" {}
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "message" {
  description = "A test message"
  type        = string
  default     = "Hello from terraform-branch-deploy"
}

# === E2E Test Variables ===
# These variables are used by E2E tests to verify -var argument handling

variable "test_var" {
  description = "Test variable for E2E tests"
  type        = string
  default     = ""
}

variable "key" {
  description = "Generic key variable for E2E tests"
  type        = string
  default     = ""
}

variable "msg" {
  description = "Message variable for E2E tests"
  type        = string
  default     = ""
}

variable "connection_string" {
  description = "Connection string variable for E2E tests"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags variable for E2E tests (JSON-style)"
  type        = any
  default     = {}
}

resource "local_file" "test" {
  content  = "Environment: ${var.environment}\nMessage: ${var.message}"
  filename = "${path.module}/output.txt"
}

output "environment" {
  value = var.environment
}

output "file_path" {
  value = local_file.test.filename
}
