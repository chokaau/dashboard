terraform {
  backend "s3" {
    bucket         = "choka-tofu-state"
    key            = "dashboard/terraform.tfstate"
    region         = "ap-southeast-2"
    dynamodb_table = "choka-tofu-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "choka-dashboard"
      ManagedBy   = "opentofu"
      Environment = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Remote state — management layer
# ---------------------------------------------------------------------------
data "terraform_remote_state" "management" {
  backend = "s3"

  config = {
    bucket = "choka-tofu-state"
    key    = "core-infrastructure/management/terraform.tfstate"
    region = "ap-southeast-2"
  }
}

# ---------------------------------------------------------------------------
# Remote state — networking layer
# ---------------------------------------------------------------------------
data "terraform_remote_state" "networking" {
  backend = "s3"

  config = {
    bucket = "choka-tofu-state"
    key    = "core-infrastructure/networking/terraform.tfstate"
    region = "ap-southeast-2"
  }
}

# ---------------------------------------------------------------------------
# Remote state — platform layer
# ---------------------------------------------------------------------------
data "terraform_remote_state" "platform" {
  backend = "s3"

  config = {
    bucket = "choka-tofu-state"
    key    = "core-infrastructure/platform/terraform.tfstate"
    region = "ap-southeast-2"
  }
}
