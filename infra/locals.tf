locals {
  name_prefix = "choka-dashboard-${var.env_short}"

  common_tags = {
    Service     = "dashboard"
    Environment = var.environment
  }

  # ---------------------------------------------------------------------------
  # Cognito — from management layer
  # ---------------------------------------------------------------------------
  cognito_user_pool_id  = data.terraform_remote_state.management.outputs.cognito_user_pool_ids[var.env_short]
  cognito_client_id     = data.terraform_remote_state.management.outputs.cognito_client_ids[var.env_short]
  cognito_user_pool_arn = "arn:aws:cognito-idp:${var.aws_region}:${data.aws_caller_identity.current.account_id}:userpool/${local.cognito_user_pool_id}"

  # ---------------------------------------------------------------------------
  # Networking — from networking layer
  # Networking — dev-only until demo/prod VPCs are provisioned in core-infrastructure.
  # See: chokaau/core-infrastructure CLAUDE.md "Adding New Environments"
  # ---------------------------------------------------------------------------
  shared_vpc_id          = data.terraform_remote_state.networking.outputs.shared_vpc_id
  dev_vpc_id             = data.terraform_remote_state.networking.outputs.dev_vpc_id
  dev_public_subnet_ids  = data.terraform_remote_state.networking.outputs.dev_public_subnet_ids
  dev_private_subnet_ids = data.terraform_remote_state.networking.outputs.dev_private_subnet_ids
  dev_fargate_sg_id      = data.terraform_remote_state.networking.outputs.dev_fargate_sg_id
  alb_listener_arn       = data.terraform_remote_state.networking.outputs.alb_listener_arn
  alb_sg_id              = data.terraform_remote_state.networking.outputs.alb_sg_id
  redis_endpoint         = data.terraform_remote_state.networking.outputs.redis_endpoint
  redis_port             = data.terraform_remote_state.networking.outputs.redis_port

  # ---------------------------------------------------------------------------
  # SPA hosting — from networking layer
  # ---------------------------------------------------------------------------
  spa_s3_bucket_name        = data.terraform_remote_state.networking.outputs.spa_s3_bucket_names[var.env_short]
  cloudfront_distribution_id = data.terraform_remote_state.networking.outputs.cloudfront_distribution_ids[var.env_short]

  # ---------------------------------------------------------------------------
  # Platform — from platform layer
  # ---------------------------------------------------------------------------
  cluster_name = data.terraform_remote_state.platform.outputs.cluster_name
  cluster_arn  = data.terraform_remote_state.platform.outputs.cluster_arn

  # ---------------------------------------------------------------------------
  # Config bucket — from management layer
  # ---------------------------------------------------------------------------
  tenant_configs_bucket_name = data.terraform_remote_state.management.outputs.tenant_configs_bucket_name

  # ---------------------------------------------------------------------------
  # Redis connection URL
  # ---------------------------------------------------------------------------
  redis_url = "redis://${local.redis_endpoint}:${local.redis_port}"

  # ---------------------------------------------------------------------------
  # CORS origins by environment
  # ---------------------------------------------------------------------------
  spa_domains = {
    dev  = "https://app.choka.dev"
    demo = "https://demo.choka.com.au"
    prod = "https://app.choka.com.au"
  }

  cors_origins = local.spa_domains[var.env_short]
}
