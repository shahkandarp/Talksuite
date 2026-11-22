# TalkSuite Backend - ECS Deployment Guide

## Prerequisites
- AWS CLI installed and configured
- Docker image pushed to ECR (`294267536771.dkr.ecr.us-east-1.amazonaws.com/talksuite-backend:latest`)
- RDS database running with migrations applied
- Parameter Store secrets configured at `/talksuite/production/*`

---

## Step 1: Add Missing Parameter Store Secrets

You already have `/talksuite/production/database-url`. Add these:

```bash
aws ssm put-parameter --name "/talksuite/production/jwt-secret" --value "YOUR_STRONG_JWT_SECRET_HERE" --type SecureString --region us-east-1

aws ssm put-parameter --name "/talksuite/production/aws-access-key-id" --value "YOUR_AWS_ACCESS_KEY" --type SecureString --region us-east-1

aws ssm put-parameter --name "/talksuite/production/aws-secret-access-key" --value "YOUR_AWS_SECRET_KEY" --type SecureString --region us-east-1

aws ssm put-parameter --name "/talksuite/production/bedrock-knowledge-base-id" --value "YOUR_KB_ID_OR_EMPTY" --type SecureString --region us-east-1
```

> For JWT secret, generate something strong: `openssl rand -hex 32`
> For Bedrock keys, use dummy values for now if not ready — mock mode will kick in.

---

## Step 2: Create IAM Roles

### 2a. ECS Task Execution Role (lets ECS pull image + read secrets)

```bash
aws iam create-role --role-name talksuite-ecs-execution-role --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

aws iam attach-role-policy --role-name talksuite-ecs-execution-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam put-role-policy --role-name talksuite-ecs-execution-role --policy-name TalkSuiteSSMAccess --policy-document '{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ssm:GetParameters", "ssm:GetParameter"],
    "Resource": "arn:aws:ssm:us-east-1:294267536771:parameter/talksuite/production/*"
  }]
}'
```

### 2b. ECS Task Role (lets the app call Bedrock, Transcribe, etc.)

```bash
aws iam create-role --role-name talksuite-ecs-task-role --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

aws iam put-role-policy --role-name talksuite-ecs-task-role --policy-name TalkSuiteBedrockAccess --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["transcribe:StartStreamTranscription"],
      "Resource": "*"
    }
  ]
}'
```

---

## Step 3: Create CloudWatch Log Group

```bash
aws logs create-log-group --log-group-name /ecs/talksuite-backend --region us-east-1
```

---

## Step 4: Create Security Group for ECS Tasks

First, get your default VPC ID and subnets:

```bash
aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region us-east-1
```

Note the VPC ID (e.g., `vpc-xxxxxxxx`), then:

```bash
aws ec2 create-security-group --group-name talksuite-ecs-sg --description "TalkSuite ECS Tasks" --vpc-id vpc-017dc582dd67a4b11 --region us-east-1
```

Note the Security Group ID (e.g., `sg-xxxxxxxx`), then allow inbound on port 8000:

```bash
aws ec2 authorize-security-group-ingress --group-id sg-04b80400805436366 --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region us-east-1
```

### Allow ECS to connect to RDS

Find your RDS security group:

```bash
aws rds describe-db-instances --db-instance-identifier talksuite-db-production --query "DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId" --output text --region us-east-1
```

Then allow the ECS SG to connect to RDS on port 5432:

```bash
aws ec2 authorize-security-group-ingress --group-id sg-0bdf87bbda25a5e92 --protocol tcp --port 5432 --source-group sg-04b80400805436366 --region us-east-1
```

---

## Step 5: Get Subnet IDs

```bash
aws ec2 describe-subnets --filters "Name=vpc-id,Values=<YOUR_VPC_ID>" --query "Subnets[*].[SubnetId,AvailabilityZone]" --output table --region us-east-1
```

Pick 2-3 subnets (ideally in different AZs).

---

## Step 6: Register Task Definition

```bash
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json --region us-east-1
```

---

## Step 7: Create ECS Service

```bash
aws ecs create-service \
  --cluster talksuite-cluster-production \
  --service-name talksuite-backend-service \
  --task-definition talksuite-backend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<SUBNET_1>,<SUBNET_2>],securityGroups=[<ECS_SG_ID>],assignPublicIp=ENABLED}" \
  --region us-east-1
```

---

## Step 8: Verify Deployment

Check the service is running:

```bash
aws ecs describe-services --cluster talksuite-cluster-production --services talksuite-backend-service --region us-east-1
```

Get the task's public IP:

```bash
# Get the task ARN
aws ecs list-tasks --cluster talksuite-cluster-production --service-name talksuite-backend-service --region us-east-1

# Get the ENI (network interface)
aws ecs describe-tasks --cluster talksuite-cluster-production --tasks <TASK_ARN> --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text --region us-east-1

# Get the public IP
aws ec2 describe-network-interfaces --network-interface-ids <ENI_ID> --query "NetworkInterfaces[0].Association.PublicIp" --output text --region us-east-1
```

Then test:

```bash
curl http://<PUBLIC_IP>:8000/health
```

Expected: `{"status":"healthy","service":"talksuite-backend"}`

---

## Updating the Service (after code changes)

```bash
# Rebuild and push
docker build -t talksuite-backend .
docker tag talksuite-backend:latest 294267536771.dkr.ecr.us-east-1.amazonaws.com/talksuite-backend:latest
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 294267536771.dkr.ecr.us-east-1.amazonaws.com
docker push 294267536771.dkr.ecr.us-east-1.amazonaws.com/talksuite-backend:latest

# Force new deployment
aws ecs update-service --cluster talksuite-cluster-production --service talksuite-backend-service --force-new-deployment --region us-east-1
```

---

## Troubleshooting

View container logs:
```bash
aws logs tail /ecs/talksuite-backend --follow --region us-east-1
```

If the task keeps stopping, check:
1. Security group allows outbound (default does)
2. ECS SG can reach RDS on port 5432
3. Parameter Store values are correct (especially DATABASE_URL format)
4. ECR image exists and is accessible
