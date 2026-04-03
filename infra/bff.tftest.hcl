# Plan-mode assertions for the dashboard BFF infra module.
# These run without AWS credentials against mocked provider data.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "737923405927"
      arn        = "arn:aws:iam::737923405927:user/test"
      user_id    = "AIDATEST"
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{}"
    }
  }
}

mock_provider "terraform" {}

# Override remote state data sources so the test does not need real state files.
override_data {
  target = data.terraform_remote_state.management
  values = {
    outputs = {
      cognito_user_pool_ids      = { dev = "ap-southeast-2_TESTPOOL" }
      cognito_client_ids         = { dev = "testclientid123" }
      cognito_user_pool_arns     = { dev = "arn:aws:cognito-idp:ap-southeast-2:737923405927:userpool/ap-southeast-2_TESTPOOL" }
      sns_alarms_topic_arn       = "arn:aws:sns:ap-southeast-2:737923405927:choka-alarms"
      kms_cloudwatch_key_arn     = "arn:aws:kms:ap-southeast-2:737923405927:key/test-key"
      tenant_configs_bucket_name = "choka-tenant-configs-dev"
    }
  }
}

override_data {
  target = data.terraform_remote_state.networking
  values = {
    outputs = {
      shared_vpc_id               = "vpc-shared"
      dev_vpc_id                  = "vpc-0dev00000000"
      dev_public_subnet_ids       = ["subnet-pub1", "subnet-pub2", "subnet-pub3"]
      dev_private_subnet_ids      = ["subnet-priv1", "subnet-priv2", "subnet-priv3"]
      dev_fargate_sg_id           = "sg-fargate"
      alb_arn                     = "arn:aws:elasticloadbalancing:ap-southeast-2:737923405927:loadbalancer/app/choka-alb/test"
      alb_listener_arn            = "arn:aws:elasticloadbalancing:ap-southeast-2:737923405927:listener/app/choka-alb/test/test"
      alb_sg_id                   = "sg-alb"
      redis_endpoint              = "choka-redis.abc123.0001.apse2.cache.amazonaws.com"
      redis_port                  = 6379
      spa_s3_bucket_names         = { dev = "choka-dashboard-spa-dev" }
      cloudfront_distribution_ids = { dev = "E1TESTDISTRIB" }
      acm_certificate_arn         = "arn:aws:acm:us-east-1:737923405927:certificate/test"
    }
  }
}

override_data {
  target = data.terraform_remote_state.platform
  values = {
    outputs = {
      cluster_name     = "choka-cluster-dev"
      cluster_arn      = "arn:aws:ecs:ap-southeast-2:737923405927:cluster/choka-cluster-dev"
      ecr_repo_url     = "737923405927.dkr.ecr.ap-southeast-2.amazonaws.com/choka-voice"
      alb_listener_arn = "arn:aws:elasticloadbalancing:ap-southeast-2:737923405927:listener/app/choka-alb/test/test"
    }
  }
}

# ---------------------------------------------------------------------------
# Test: ECR repository name
# ---------------------------------------------------------------------------
run "ecr_repository_name" {
  command = plan

  variables {
    env_short     = "dev"
    environment   = "development"
    desired_count = 0
    use_spot      = true
  }

  assert {
    condition     = aws_ecr_repository.dashboard_api.name == "choka-dashboard-api"
    error_message = "ECR repository name must be 'choka-dashboard-api', got: ${aws_ecr_repository.dashboard_api.name}"
  }
}

# ---------------------------------------------------------------------------
# Test: ECS task definition family name
# ---------------------------------------------------------------------------
run "task_definition_family" {
  command = plan

  variables {
    env_short     = "dev"
    environment   = "development"
    desired_count = 0
    use_spot      = true
  }

  assert {
    condition     = aws_ecs_task_definition.bff.family == "choka-dashboard-dev-bff"
    error_message = "Task family must be 'choka-dashboard-dev-bff', got: ${aws_ecs_task_definition.bff.family}"
  }
}

# ---------------------------------------------------------------------------
# Test: CloudWatch log group name
# ---------------------------------------------------------------------------
run "log_group_name" {
  command = plan

  variables {
    env_short     = "dev"
    environment   = "development"
    desired_count = 0
    use_spot      = true
  }

  assert {
    condition     = aws_cloudwatch_log_group.bff.name == "/ecs/dashboard-bff/dev"
    error_message = "Log group must be '/ecs/dashboard-bff/dev', got: ${aws_cloudwatch_log_group.bff.name}"
  }
}

# ---------------------------------------------------------------------------
# Test: desired_count defaults to 0
# ---------------------------------------------------------------------------
run "desired_count_defaults_to_zero" {
  command = plan

  variables {
    env_short   = "dev"
    environment = "development"
  }

  assert {
    condition     = aws_ecs_service.bff.desired_count == 0
    error_message = "desired_count must default to 0, got: ${aws_ecs_service.bff.desired_count}"
  }
}

# ---------------------------------------------------------------------------
# Test: desired_count is honoured when set explicitly
# ---------------------------------------------------------------------------
run "desired_count_overridable" {
  command = plan

  variables {
    env_short     = "dev"
    environment   = "development"
    desired_count = 2
    use_spot      = true
  }

  assert {
    condition     = aws_ecs_service.bff.desired_count == 2
    error_message = "desired_count must be 2 when explicitly set, got: ${aws_ecs_service.bff.desired_count}"
  }
}
