# ---------------------------------------------------------------------------
# CloudWatch log group
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "bff" {
  name              = "/ecs/dashboard-bff/${var.env_short}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# IAM — execution role (ECS pulls image, reads secrets)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bff_execution" {
  name               = "${local.name_prefix}-bff-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "bff_execution_ecr" {
  role       = aws_iam_role.bff_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "bff_execution_secrets" {
  statement {
    sid     = "ReadSecrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      var.cloudfront_origin_secret_arn,
    ])
  }
}

resource "aws_iam_role_policy" "bff_execution_secrets" {
  count  = var.cloudfront_origin_secret_arn != "" ? 1 : 0
  name   = "read-cloudfront-secret"
  role   = aws_iam_role.bff_execution.name
  policy = data.aws_iam_policy_document.bff_execution_secrets.json
}

# ---------------------------------------------------------------------------
# IAM — task role (application runtime permissions)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "bff_task" {
  name               = "${local.name_prefix}-bff-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

data "aws_iam_policy_document" "bff_task" {
  statement {
    sid     = "ReadTenantConfigs"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${local.tenant_configs_bucket_name}",
      "arn:aws:s3:::${local.tenant_configs_bucket_name}/*",
    ]
  }

  statement {
    sid     = "WriteTenantRegistration"
    actions = ["s3:PutObject"]
    resources = [
      "arn:aws:s3:::${local.tenant_configs_bucket_name}/*",
    ]
  }

  statement {
    sid     = "CognitoTenantAdmin"
    actions = [
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminUpdateUserAttributes",
    ]
    resources = [
      local.cognito_user_pool_arn,
    ]
  }
}

resource "aws_iam_role_policy" "bff_task" {
  name   = "s3-cognito-tenant-ops"
  role   = aws_iam_role.bff_task.name
  policy = data.aws_iam_policy_document.bff_task.json
}

# ---------------------------------------------------------------------------
# ECS task definition
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "bff" {
  family                   = "${local.name_prefix}-bff"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.bff_execution.arn
  task_role_arn            = aws_iam_role.bff_task.arn

  container_definitions = jsonencode([
    {
      name      = "bff"
      image     = "${local.ecr_repo_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "PORT", value = "8000" },
        { name = "NODE_ENV", value = var.environment },
        { name = "COGNITO_USER_POOL_ID", value = local.cognito_user_pool_id },
        { name = "COGNITO_CLIENT_ID", value = local.cognito_client_id },
        { name = "REDIS_URL", value = local.redis_url },
        { name = "CORS_ORIGINS", value = local.cors_origins },
        { name = "TENANT_CONFIGS_BUCKET", value = local.tenant_configs_bucket_name },
      ]

      secrets = var.cloudfront_origin_secret_arn != "" ? [
        {
          name      = "CLOUDFRONT_ORIGIN_SECRET"
          valueFrom = var.cloudfront_origin_secret_arn
        }
      ] : []

      linuxParameters = {
        readonlyRootFilesystem = true
        tmpfs = [
          {
            containerPath = "/tmp"
            size          = 64
          }
        ]
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -sf http://localhost:8000/api/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.bff.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "bff"
        }
      }
    }
  ])
}

# ---------------------------------------------------------------------------
# ALB target group
# ---------------------------------------------------------------------------
resource "aws_lb_target_group" "bff" {
  name        = "${local.name_prefix}-bff"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.shared_vpc_id

  health_check {
    path                = "/api/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ---------------------------------------------------------------------------
# ALB listener rule — /api/*
# ---------------------------------------------------------------------------
resource "aws_lb_listener_rule" "bff" {
  listener_arn = local.alb_listener_arn
  priority     = var.listener_rule_priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.bff.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# ---------------------------------------------------------------------------
# ECS service
# ---------------------------------------------------------------------------
resource "aws_ecs_service" "bff" {
  name            = "${local.name_prefix}-bff"
  cluster         = local.cluster_arn
  task_definition = aws_ecs_task_definition.bff.arn
  desired_count   = var.desired_count
  launch_type     = null

  capacity_provider_strategy {
    capacity_provider = var.use_spot ? "FARGATE_SPOT" : "FARGATE"
    weight            = 1
    base              = 0
  }

  network_configuration {
    subnets          = local.dev_public_subnet_ids
    security_groups  = [local.dev_fargate_sg_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.bff.arn
    container_name   = "bff"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_controller {
    type = "ECS"
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
    precondition {
      condition     = var.env_short == "dev" || var.desired_count == 0
      error_message = "Only dev environment has provisioned VPC/subnets. Set desired_count = 0 for ${var.env_short} until networking is ready."
    }
  }
}
