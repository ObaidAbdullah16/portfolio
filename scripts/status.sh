#!/usr/bin/env bash
# Show where the portfolio is published and whether it answers.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need aws terraform curl
TF="$REPO_ROOT/infra"
tf_init "$TF" "portfolio/terraform.tfstate"
if ! tf_has_resources "$TF"; then
  echo "portfolio: DOWN (website not deployed - start: bash scripts/up.sh)"
  exit 0
fi
url="$(tf_out "$TF" url)"
echo "portfolio: UP $url (always on, ~\$0/month; Route 53 zone \$0.50/month if you use the domain)"
echo "HTTP status: $(curl -s -o /dev/null -w '%{http_code}' "$url/")"
echo "Last upload: $(aws s3api head-object --bucket "$(tf_out "$TF" bucket)" --key index.html --query LastModified --output text 2>/dev/null || echo unknown)"
