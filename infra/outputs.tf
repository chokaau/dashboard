output "cognito_user_pool_id" {
  description = "Cognito User Pool ID for this environment"
  value       = local.cognito_user_pool_id
}

output "cognito_client_id" {
  description = "Cognito App Client ID for this environment"
  value       = local.cognito_client_id
}

output "spa_s3_bucket_name" {
  description = "S3 bucket name hosting the SPA assets for this environment"
  value       = local.spa_s3_bucket_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID fronting the SPA for this environment"
  value       = local.cloudfront_distribution_id
}

output "ecr_repo_url" {
  description = "ECR repository URL for the dashboard BFF container image"
  value       = local.ecr_repo_url
}

output "bff_service_name" {
  description = "ECS service name for the BFF"
  value       = aws_ecs_service.bff.name
}

output "bff_log_group" {
  description = "CloudWatch log group name for BFF task logs"
  value       = aws_cloudwatch_log_group.bff.name
}
