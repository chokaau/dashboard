# ECR repository is shared across environments — only created by the dev apply.
# Demo/prod reference the same repo by name.
resource "aws_ecr_repository" "dashboard_api" {
  count                = var.env_short == "dev" ? 1 : 0
  name                 = "choka-dashboard-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "dashboard_api" {
  count      = var.env_short == "dev" ? 1 : 0
  repository = aws_ecr_repository.dashboard_api[0].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

data "aws_ecr_repository" "dashboard_api" {
  count = var.env_short != "dev" ? 1 : 0
  name  = "choka-dashboard-api"
}

locals {
  ecr_repo_url = var.env_short == "dev" ? aws_ecr_repository.dashboard_api[0].repository_url : data.aws_ecr_repository.dashboard_api[0].repository_url
}
