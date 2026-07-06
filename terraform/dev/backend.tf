terraform {
  backend "s3" {
    bucket = "nonexistent-bucket-12345"
    key = "test.tfstate"
    region = "us-east-1"
  }
}
