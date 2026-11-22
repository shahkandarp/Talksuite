# =============================================================================
# S3 — Knowledge Base Document Storage
# =============================================================================
# Bucket for documents that back the AWS Bedrock Knowledge Base (RAG).
# Documents uploaded here are indexed by Bedrock for retrieval.
# =============================================================================

resource "aws_s3_bucket" "knowledge_base_docs" {
  bucket        = "${var.project_name}-kb-docs-${var.environment}-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.environment != "production"

  tags = {
    Name = "${var.project_name}-kb-docs-${var.environment}"
  }
}

resource "aws_s3_bucket_versioning" "knowledge_base_docs" {
  bucket = aws_s3_bucket.knowledge_base_docs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "knowledge_base_docs" {
  bucket = aws_s3_bucket.knowledge_base_docs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "knowledge_base_docs" {
  bucket = aws_s3_bucket.knowledge_base_docs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
