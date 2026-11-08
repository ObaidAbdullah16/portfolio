#!/usr/bin/env bash
# Deploy the portfolio: Terraform (S3 + CloudFront), build the site, upload it,
# connect the IncidentScribe live demo and invalidate the CDN cache.
# Safe to run as often as you like; this is also what the Deploy workflow runs.
# Cost: practically $0 (CloudFront always-free tier, a few MB in S3).
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need aws terraform python3
TF="$REPO_ROOT/infra"

log "Terraform apply (first run: CloudFront takes ~5 minutes)"
tf_init "$TF" "portfolio/terraform.tfstate"
use_custom_domain_from_config
tf_apply "$TF" >/dev/null
url="$(tf_out "$TF" url)"; bucket="$(tf_out "$TF" bucket)"; dist_id="$(tf_out "$TF" distribution_id)"

log "Building the site"
SITE_URL="$url" python3 "$REPO_ROOT/build.py"

api="$(aws ssm get-parameter --name /incidentscribe/api-url --query Parameter.Value --output text 2>/dev/null || true)"
if [[ "$api" == https://* ]]; then
  printf 'window.INCIDENTSCRIBE_API = "%s";\n' "$api" > "$REPO_ROOT/dist/demos/incidentscribe/config.js"
  log "IncidentScribe live demo connected to $api"
else
  warn "IncidentScribe is not deployed yet - its demo page will say 'API URL not configured'"
fi

log "Uploading to s3://$bucket"
# Assets: cache for a day. HTML: always revalidate so changes show up at once.
aws s3 sync "$REPO_ROOT/dist" "s3://$bucket" --delete --exclude "*.html" \
  --cache-control "public, max-age=86400" --only-show-errors
aws s3 sync "$REPO_ROOT/dist" "s3://$bucket" --delete --exclude "*" --include "*.html" \
  --cache-control "public, max-age=0, must-revalidate" --content-type "text/html; charset=utf-8" --only-show-errors
aws cloudfront create-invalidation --distribution-id "$dist_id" --paths "/*" --query Invalidation.Id --output text >/dev/null

log "Portfolio is live: $url"
