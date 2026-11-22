# =============================================================================
# TalkSuite Backend - Terraform Infrastructure
# =============================================================================
# This configuration provisions all AWS resources needed to run the TalkSuite
# backend: VPC networking, RDS PostgreSQL, ECS Fargate, ALB, Bedrock access,
# ECR, and supporting IAM/secrets infrastructure.
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment and configure for remote state
  # backend "s3" {
  #   bucket         = "talksuite-terraform-state"
  #   key            = "backend/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "talksuite-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "TalkSuite"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
