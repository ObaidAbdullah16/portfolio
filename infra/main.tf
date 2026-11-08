# Portfolio hosting: private S3 bucket + CloudFront (Origin Access Control).
# Always on and practically free: CloudFront's always-free tier covers 1 TB and
# 10 million requests a month; the bucket holds a few MB.
terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {}
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "domain_name" {
  description = "Optional custom domain (e.g. obaidabdullah.com). Needs hosted_zone_id."
  type        = string
  default     = ""
}

variable "extra_domain_names" {
  description = "Other names that serve the same site, e.g. [\"www.obaidabdullah.com\"]. Must be in the same hosted zone."
  type        = list(string)
  default     = []
}

variable "hosted_zone_id" {
  description = "Optional Route 53 hosted zone that contains domain_name."
  type        = string
  default     = ""
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "portfolio"
      ManagedBy = "terraform"
    }
  }
}

# CloudFront only accepts ACM certificates from us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      Project   = "portfolio"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  custom_domain = var.domain_name != "" && var.hosted_zone_id != ""
}

resource "aws_s3_bucket" "site" {
  bucket        = "portfolio-site-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # the content is rebuilt from Git on every deploy
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "portfolio-site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Strict security headers (CSP allows only this site plus the IncidentScribe API).
resource "aws_cloudfront_response_headers_policy" "security" {
  name = "portfolio-security-headers"
  security_headers_config {
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_security_policy {
      content_security_policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://*.execute-api.${var.aws_region}.amazonaws.com https://api.web3forms.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://api.web3forms.com"
      override                = true
    }
  }
}

# S3 behind Origin Access Control has no "index document": a link to
# /tools/bedrock-calculator/ would ask S3 for a key that doesn't exist (and show
# the 404 page). This function serves index.html for directory URLs, and
# redirects /path to /path/ so that relative links inside that page still work.
resource "aws_cloudfront_function" "directory_index" {
  name    = "portfolio-directory-index"
  runtime = "cloudfront-js-2.0"
  comment = "Serve index.html for directory URLs"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      if (uri.endsWith("/")) {
        request.uri = uri + "index.html";
        return request;
      }
      var last = uri.substring(uri.lastIndexOf("/") + 1);
      if (last.indexOf(".") === -1) {
        return {
          statusCode: 301,
          statusDescription: "Moved Permanently",
          headers: { location: { value: uri + "/" } }
        };
      }
      return request;
    }
  EOT
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_acm_certificate" "site" {
  count                     = local.custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = var.extra_domain_names
  validation_method         = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  for_each = local.custom_domain ? {
    for o in aws_acm_certificate.site[0].domain_validation_options : o.domain_name => o
  } : {}
  zone_id         = var.hosted_zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  count                   = local.custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Portfolio"
  default_root_object = "index.html"
  price_class         = "PriceClass_200" # includes India; excludes the most expensive edges
  aliases             = local.custom_domain ? concat([var.domain_name], var.extra_domain_names) : []
  http_version        = "http2and3"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id           = "s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.directory_index.arn
    }
  }

  custom_error_response {
    error_code         = 403 # S3 answers 403 for missing keys when listing is not allowed
    response_code      = 404
    response_page_path = "/404.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 404
    response_page_path = "/404.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = !local.custom_domain
    acm_certificate_arn            = local.custom_domain ? aws_acm_certificate_validation.site[0].certificate_arn : null
    ssl_support_method             = local.custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }
}

data "aws_iam_policy_document" "site" {
  statement {
    sid       = "CloudFrontReadOnly"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}

resource "aws_route53_record" "site" {
  for_each = local.custom_domain ? {
    for pair in setproduct(concat([var.domain_name], var.extra_domain_names), ["A", "AAAA"]) : "${pair[0]}|${pair[1]}" => { name = pair[0], type = pair[1] }
  } : {}
  zone_id = var.hosted_zone_id
  name    = each.value.name
  type    = each.value.type
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

output "bucket" {
  value = aws_s3_bucket.site.id
}

output "distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "url" {
  value = local.custom_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.site.domain_name}"
}
