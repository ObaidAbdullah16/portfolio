#!/usr/bin/env bash
# Shared helpers for this repo's up/down/status scripts. Sourced, not executed.
# Settings come from the environment, or from ../_setup/config.env when this repo
# sits inside the Projects_Demos folder.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$REPO_ROOT/../_setup/config.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/../_setup/config.env"
fi
: "${AWS_REGION:=ap-southeast-2}"
: "${AUTO_APPROVE:=1}"          # set AUTO_APPROVE=0 to review the plan before applying
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"
[[ -n "${AWS_PROFILE:-}" ]] && export AWS_PROFILE
: "${GITHUB_OWNER:=ObaidAbdullah16}"
CONFIG_FILE="${CONFIG_FILE:-$REPO_ROOT/../_setup/config.env}"

log()  { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

need() {
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || die "'$c' is not installed (see _setup/install-tools-wsl.sh)"
  done
}

aws_account_id() { aws sts get-caller-identity --query Account --output text; }

state_bucket() { echo "${TF_STATE_BUCKET:-tfstate-$(aws_account_id)-${AWS_REGION}}"; }

# tf_init <terraform dir> <state key>
tf_init() {
  local dir="$1" key="$2" bucket
  bucket="$(state_bucket)"
  aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1 \
    || die "State bucket $bucket not found: the AWS foundation is not set up (or you are logged in to another account). Start it first: bash _setup/projects.sh up foundation"
  terraform -chdir="$dir" init -input=false -reconfigure \
    -backend-config="bucket=${bucket}" \
    -backend-config="key=${key}" \
    -backend-config="region=${AWS_REGION}" \
    -backend-config="use_lockfile=true" \
    -backend-config="encrypt=true" >/dev/null
}

tf_apply() { # tf_apply <dir> [extra args...]
  local dir="$1"; shift
  if [[ "$AUTO_APPROVE" == "1" ]]; then
    terraform -chdir="$dir" apply -input=false -auto-approve -var "aws_region=${AWS_REGION}" "$@"
  else
    terraform -chdir="$dir" apply -input=false -var "aws_region=${AWS_REGION}" "$@"
  fi
}

tf_destroy() { # tf_destroy <dir> [extra args...]
  local dir="$1"; shift
  if [[ "$AUTO_APPROVE" == "1" ]]; then
    terraform -chdir="$dir" destroy -input=false -auto-approve -var "aws_region=${AWS_REGION}" "$@"
  else
    terraform -chdir="$dir" destroy -input=false -var "aws_region=${AWS_REGION}" "$@"
  fi
}

tf_out() { terraform -chdir="$1" output -raw "$2" 2>/dev/null || true; }

# Is anything in this Terraform state? (used by status / auto-stop)
tf_has_resources() { [[ -n "$(terraform -chdir="$1" state list 2>/dev/null | grep -v '^data\.' || true)" ]]; }

# ------------------------------------------------------------------ custom domain
# Is <domain> served by Route 53 yet (the registrar points at the awsdns name servers)?
# domain_delegated <domain> [hosted zone id]: true when the internet already asks THIS hosted zone
# about the domain - its public name servers are exactly the zone's four name servers. (Checking
# for "awsdns" is not enough: an old zone in another AWS account also has awsdns name servers.)
domain_delegated() {
  local d="$1" z="${2:-${PORTFOLIO_ZONE_ID:-}}" got want
  command -v dig >/dev/null 2>&1 || { warn "dig is not installed (sudo apt-get install -y dnsutils)"; return 1; }
  got="$(dig +short NS "$d" @1.1.1.1 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed 's/\.$//' | sort -u)"
  [[ -n "$got" ]] || got="$(dig +short NS "$d" 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed 's/\.$//' | sort -u)"
  if [[ -n "$z" ]]; then
    want="$(aws route53 get-hosted-zone --id "$z" --query DelegationSet.NameServers --output text 2>/dev/null \
      | tr '\t' '\n' | tr '[:upper:]' '[:lower:]' | sed 's/\.$//' | sort -u)"
    [[ -n "$want" && "$got" == "$want" ]]
  else
    grep -q 'awsdns-' <<<"$got"
  fi
}

# On GitHub, the Deploy workflow passes the domain as TF_VAR_* from repository variables.
# On your laptop, use PORTFOLIO_DOMAIN / PORTFOLIO_ZONE_ID / PORTFOLIO_EXTRA_DOMAINS from
# _setup/config.env - but only once the domain points at Route 53, otherwise the HTTPS
# certificate can never be validated.
use_custom_domain_from_config() {
  [[ -n "${TF_VAR_domain_name+x}" ]] && return 0          # already decided (GitHub Actions)
  [[ -n "${PORTFOLIO_DOMAIN:-}" && -n "${PORTFOLIO_ZONE_ID:-}" ]] || return 0
  # Already live on the domain? Keep it, even if a DNS lookup fails right now.
  if terraform -chdir="$REPO_ROOT/infra" state list 2>/dev/null | grep -q 'aws_acm_certificate' || domain_delegated "$PORTFOLIO_DOMAIN"; then
    export TF_VAR_domain_name="$PORTFOLIO_DOMAIN" TF_VAR_hosted_zone_id="$PORTFOLIO_ZONE_ID"
    export TF_VAR_extra_domain_names="${PORTFOLIO_EXTRA_DOMAINS:-[]}"
    log "Custom domain: https://$PORTFOLIO_DOMAIN (from _setup/config.env)"
  else
    warn "$PORTFOLIO_DOMAIN does not point at Route 53 yet - deploying on the CloudFront address only."
    warn "Change the name servers at your registrar (Portfolio guide, section 'Domain'), then run this again."
  fi
}

# set_config KEY VALUE: write a setting into _setup/config.env (creates the line if missing)
set_config() {
  local key="$1" val="$2"
  [[ -f "$CONFIG_FILE" ]] || return 0
  python3 - "$CONFIG_FILE" "$key" "$val" <<'PY'
import re, sys
path, key, val = sys.argv[1:]
text = open(path).read()
line = f"{key}='{val}'" if any(c in val for c in ' "[]') else f"{key}={val}"
if re.search(rf"^{key}=.*$", text, flags=re.M):
    text = re.sub(rf"^{key}=.*$", lambda m: line, text, flags=re.M)
else:
    text = text.rstrip("\n") + "\n" + line + "\n"
open(path, "w").write(text)
PY
}

gh_ready() { command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; }
in_ci() { [[ -n "${GITHUB_ACTIONS:-}" ]]; }
