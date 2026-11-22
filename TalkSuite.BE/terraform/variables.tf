# =============================================================================
# Variables
# =============================================================================

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (development, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "talksuite"
}

# Networking
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# Database
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "talksuite"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "talksuite_admin"
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum RDS autoscaling storage in GB"
  type        = number
  default     = 100
}

# ECS / Fargate
variable "app_cpu" {
  description = "Fargate task CPU units (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "app_memory" {
  description = "Fargate task memory in MiB (512, 1024, 2048, ...)"
  type        = number
  default     = 1024
}

variable "app_desired_count" {
  description = "Number of desired ECS tasks"
  type        = number
  default     = 2
}

variable "app_port" {
  description = "Port the application listens on"
  type        = number
  default     = 8000
}

variable "app_image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# Bedrock
variable "bedrock_model_id" {
  description = "AWS Bedrock model identifier"
  type        = string
  default     = "anthropic.claude-3-sonnet-20240229-v1:0"
}

variable "bedrock_knowledge_base_id" {
  description = "AWS Bedrock Knowledge Base ID"
  type        = string
  default     = ""
}

# MCP
variable "netsuite_mcp_url" {
  description = "URL of the NetSuite MCP Server (auto-built from account ID if empty)"
  type        = string
  default     = ""
}

variable "netsuite_account_id" {
  description = "NetSuite Account ID (e.g., 1234567 or TSTDRV1234567)"
  type        = string
  default     = ""
}

variable "netsuite_client_id" {
  description = "NetSuite OAuth 2.0 Client ID from the Integration Record"
  type        = string
  default     = ""
  sensitive   = true
}

variable "netsuite_refresh_token" {
  description = "NetSuite OAuth 2.0 Refresh Token (obtained via one-time PKCE browser flow)"
  type        = string
  default     = ""
  sensitive   = true
}

# Auto-scaling
variable "autoscale_min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "autoscale_max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 4
}

variable "autoscale_cpu_target" {
  description = "Target CPU utilization for autoscaling (percent)"
  type        = number
  default     = 70
}

# Domain (optional)
variable "domain_name" {
  description = "Custom domain name for the ALB (leave empty to skip)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS (required if domain_name is set)"
  type        = string
  default     = ""
}

# Frontend
variable "frontend_domain_name" {
  description = "Custom domain name for the CloudFront distribution (leave empty to use default CloudFront domain)"
  type        = string
  default     = ""
}

variable "frontend_certificate_arn" {
  description = "ACM certificate ARN for frontend HTTPS (must be in us-east-1 for CloudFront)"
  type        = string
  default     = ""
}
