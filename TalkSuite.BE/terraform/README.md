# TalkSuite Backend — Terraform Infrastructure

This directory contains Terraform configurations to provision the complete AWS infrastructure for the TalkSuite backend.

## Architecture

```
                    Internet
                       │
                ┌──────▼──────┐
                │     ALB      │  (Public subnets)
                └──────┬──────┘
                       │
          ┌────────────▼────────────┐
          │    ECS Fargate Tasks    │  (Private subnets)
          │   ┌─────┐  ┌─────┐    │
          │   │App 1│  │App 2│    │
          │   └──┬──┘  └──┬──┘    │
          └──────┼────────┼────────┘
                 │        │
    ┌────────────▼────────▼───┐
    │     RDS PostgreSQL 16   │  (Private subnets)
    └─────────────────────────┘

    External: AWS Bedrock (LLM + KB), NetSuite MCP Server
```

## Resources Provisioned

| Resource | Description |
|----------|-------------|
| VPC | Isolated network with public/private subnets across 2 AZs |
| ALB | Application Load Balancer with health checks |
| ECS Cluster | Fargate cluster with auto-scaling |
| RDS PostgreSQL 16 | Managed database with encryption at rest |
| ECR | Container registry for Docker images |
| S3 | Document bucket for Bedrock Knowledge Base |
| IAM | Least-privilege roles for ECS tasks (Bedrock access) |
| SSM Parameter Store | Secure storage for database credentials |
| CloudWatch | Log group for application logs |

## Prerequisites

1. [Terraform CLI](https://developer.hashicorp.com/terraform/install) >= 1.5.0
2. AWS CLI configured with appropriate credentials
3. Docker (for building and pushing images)

## Quick Start

```bash
# 1. Initialize Terraform
cd terraform
terraform init

# 2. Create your variables file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 3. Plan the deployment
terraform plan

# 4. Apply (creates all resources)
terraform apply

# 5. Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_URL>
docker build -t talksuite-backend ..
docker tag talksuite-backend:latest <ECR_URL>:latest
docker push <ECR_URL>:latest

# 6. Force new deployment (after pushing new image)
aws ecs update-service --cluster talksuite-cluster-production --service talksuite-service-production --force-new-deployment
```

## Environment-Specific Deployments

Use Terraform workspaces or separate `.tfvars` files per environment:

```bash
# Development
terraform apply -var-file="environments/dev.tfvars"

# Production
terraform apply -var-file="environments/prod.tfvars"
```

## Running Database Migrations

After the first deployment, run Alembic migrations against the RDS instance. Use ECS exec or a one-off task:

```bash
# Option 1: ECS Exec into a running task
aws ecs execute-command --cluster talksuite-cluster-production \
  --task <TASK_ID> --container talksuite-app \
  --interactive --command "alembic upgrade head"

# Option 2: Run a one-off migration task (recommended for CI/CD)
# Use the same task definition but override the command
```

## Destroying Infrastructure

```bash
# WARNING: This will destroy ALL resources including the database
terraform destroy
```

For production, `deletion_protection` is enabled on the RDS instance and ALB. You'll need to disable that first via the AWS Console or by setting the variables.

## Cost Estimate (us-east-1, approximate)

| Resource | Monthly Cost |
|----------|-------------|
| ECS Fargate (2 tasks, 0.5 vCPU, 1GB) | ~$30 |
| RDS db.t3.micro (single-AZ) | ~$15 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| S3 + ECR | ~$2 |
| CloudWatch Logs | ~$3 |
| **Total (dev/staging)** | **~$105/mo** |

Production with multi-AZ RDS, larger instances, and more tasks will be higher.

## Remote State (Optional)

Uncomment the `backend "s3"` block in `main.tf` and create the state bucket:

```bash
aws s3 mb s3://talksuite-terraform-state
aws dynamodb create-table \
  --table-name talksuite-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```
