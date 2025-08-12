provider "aws" {
  region  = "us-west-1"
  profile = "myprofile"
}


resource "aws_ecr_repository" "cloud_monitoring_repo" {
  name                 = "cloud-monitoring-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

