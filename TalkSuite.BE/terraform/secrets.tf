# =============================================================================
# SSM Parameters & Secrets
# =============================================================================
# Sensitive configuration values stored in SSM Parameter Store.
# The ECS task execution role has permission to read these at startup.
# =============================================================================

resource "aws_ssm_parameter" "database_url" {
  name        = "/${var.project_name}/${var.environment}/database-url"
  description = "PostgreSQL connection string for TalkSuite backend"
  type        = "SecureString"
  value       = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.endpoint}/${var.db_name}"

  tags = {
    Name = "${var.project_name}-db-url-${var.environment}"
  }
}

resource "aws_ssm_parameter" "netsuite_mcp_url" {
  name        = "/${var.project_name}/${var.environment}/netsuite-mcp-url"
  description = "NetSuite MCP Server URL for TalkSuite backend"
  type        = "String"
  value       = var.netsuite_mcp_url

  tags = {
    Name = "${var.project_name}-mcp-url-${var.environment}"
  }
}

resource "aws_ssm_parameter" "netsuite_account_id" {
  name        = "/${var.project_name}/${var.environment}/netsuite-account-id"
  description = "NetSuite Account ID"
  type        = "String"
  value       = var.netsuite_account_id

  tags = {
    Name = "${var.project_name}-netsuite-account-${var.environment}"
  }
}

resource "aws_ssm_parameter" "netsuite_client_id" {
  name        = "/${var.project_name}/${var.environment}/netsuite-client-id"
  description = "NetSuite OAuth 2.0 Client ID (from Integration Record)"
  type        = "SecureString"
  value       = var.netsuite_client_id

  tags = {
    Name = "${var.project_name}-netsuite-client-id-${var.environment}"
  }
}

resource "aws_ssm_parameter" "netsuite_refresh_token" {
  name        = "/${var.project_name}/${var.environment}/netsuite-refresh-token"
  description = "NetSuite OAuth 2.0 Refresh Token"
  type        = "SecureString"
  value       = var.netsuite_refresh_token

  tags = {
    Name = "${var.project_name}-netsuite-refresh-token-${var.environment}"
  }
}
