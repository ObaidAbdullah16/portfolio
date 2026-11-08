#!/usr/bin/env bash
# Set up a custom domain for the portfolio in Route 53, plus email forwarding records.
#
#   bash scripts/domain-setup.sh obaidabdullah.com              # dry run: shows what it would change
#   bash scripts/domain-setup.sh obaidabdullah.com --apply      # step 1: hosted zone + records, prints 4 name servers
#   (change the name servers at your registrar, wait until they show up)
#   bash scripts/domain-setup.sh obaidabdullah.com --connect    # step 2: checks the name servers, sets the GitHub
#                                                            # variables and redeploys the site on the domain
# Moving the domain from a zone in ANOTHER AWS account? Between step 1 and the name-server change, copy the
# records you want to keep: bash scripts/copy-dns-records.sh <domain> (only when moving a domain between accounts).
#
# What it does (idempotent - safe to run again):
#   1. Finds the public hosted zone for the domain, or creates it ($0.50/month), and saves
#      PORTFOLIO_DOMAIN / PORTFOLIO_ZONE_ID in _setup/config.env.
#   2. Prints the four name servers to paste at your registrar.
#   3. Upserts records for email forwarding with ImprovMX (free plan, receive only):
#        MX 10 mx1.improvmx.com, MX 20 mx2.improvmx.com, SPF "v=spf1 include:spf.improvmx.com ~all",
#        DMARC "v=DMARC1; p=none; rua=mailto:dmarc@<domain>" (monitoring first; see lifeline's runbook),
#        CAA 0 issue "amazon.com" (only Amazon may issue certificates; ACM issues the site's certificate).
#      Other TXT values on the apex (site verifications) are kept; an older SPF value is replaced.
#   4. With --connect (alias: --github-vars), once the domain points at Route 53: sets PORTFOLIO_DOMAIN,
#      PORTFOLIO_ZONE_ID and PORTFOLIO_EXTRA_DOMAINS on the portfolio repo, INCIDENTSCRIBE_ALLOWED_ORIGINS on
#      incidentscribe-ai and PORTFOLIO_URL on bedrock-cost-calculator, then deploys the site on the domain:
#      the Deploy workflow (classic account) or scripts/up.sh on this laptop (project account).
# The website records (A/AAAA for the apex and www) are created by Terraform during that deploy.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DOMAIN="${1:?usage: domain-setup.sh <domain> [--apply] [--connect] [--no-email]}"
shift
APPLY=0 GHVARS=0 EMAIL=1
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --connect|--github-vars) GHVARS=1 ;;
    --no-email) EMAIL=0 ;;
    *) die "unknown option: $a" ;;
  esac
done
need aws python3
REPO="${GITHUB_OWNER:-ObaidAbdullah16}/portfolio"

zone_id() {
  aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN." --max-items 1 \
    --query "HostedZones[?Name=='$DOMAIN.' && Config.PrivateZone==\`false\`].Id | [0]" --output text | sed 's|/hostedzone/||; s|^None$||'
}

ZONE="$(zone_id)"
if [[ -z "$ZONE" ]]; then
  if [[ "$APPLY" != 1 ]]; then
    log "Dry run: would create the public hosted zone $DOMAIN (\$0.50/month). Re-run with --apply."
    exit 0
  fi
  log "Creating the public hosted zone $DOMAIN..."
  ZONE="$(aws route53 create-hosted-zone --name "$DOMAIN" --caller-reference "portfolio-$(date +%s)" \
    --hosted-zone-config Comment="portfolio (created by domain-setup.sh)" --query HostedZone.Id --output text | sed 's|/hostedzone/||')"
fi
log "Hosted zone: $ZONE"
if [[ "$APPLY" == 1 ]]; then
  set_config PORTFOLIO_DOMAIN "$DOMAIN"
  set_config PORTFOLIO_ZONE_ID "$ZONE"
  set_config PORTFOLIO_EXTRA_DOMAINS "[\"www.$DOMAIN\"]"
fi
echo
echo "Name servers - paste all four at your registrar (custom DNS / nameservers), without the trailing dot:"
aws route53 get-hosted-zone --id "$ZONE" --query DelegationSet.NameServers --output text | tr '\t' '\n' | sed 's/^/  /'
echo

if [[ "$EMAIL" == 1 && ( "$APPLY" == 1 || "$GHVARS" == 0 ) ]]; then
  CURRENT_TXT="$(aws route53 list-resource-record-sets --hosted-zone-id "$ZONE" --start-record-name "$DOMAIN." \
    --start-record-type TXT --max-items 1 --output json)"
  BATCH="$(DOMAIN="$DOMAIN" CURRENT="$CURRENT_TXT" python3 - <<'PY'
import json, os
d = os.environ["DOMAIN"].rstrip(".") + "."
cur = json.loads(os.environ["CURRENT"]).get("ResourceRecordSets", [])
apex_txt = [r["Value"] for s in cur if s["Name"] == d and s["Type"] == "TXT" for r in s.get("ResourceRecords", [])]
spf = '"v=spf1 include:spf.improvmx.com ~all"'
txt = [v for v in apex_txt if not v.strip('"').startswith("v=spf1")] + [spf]
def rrset(name, rtype, values, ttl=3600):
    return {"Action": "UPSERT", "ResourceRecordSet": {"Name": name, "Type": rtype, "TTL": ttl,
            "ResourceRecords": [{"Value": v} for v in values]}}
changes = [
    rrset(d, "MX", ["10 mx1.improvmx.com.", "20 mx2.improvmx.com."]),
    rrset(d, "TXT", txt),
    rrset("_dmarc." + d, "TXT", [f'"v=DMARC1; p=none; rua=mailto:dmarc@{d.rstrip(".")}; fo=1"']),
    rrset(d, "CAA", ['0 issue "amazon.com"']),
]
print(json.dumps({"Comment": "email forwarding (ImprovMX), DMARC monitoring, CAA", "Changes": changes}))
PY
)"
  if [[ "$APPLY" == 1 ]]; then
    log "Upserting MX, SPF, DMARC and CAA records..."
    status="$(aws route53 change-resource-record-sets --hosted-zone-id "$ZONE" --change-batch "$BATCH" --query ChangeInfo.Status --output text)"
    log "Records saved in Route 53 (change status: $status)"
  else
    log "Dry run - these records would be upserted (re-run with --apply):"
    python3 -c 'import json,sys; [print("  %-28s %-4s %s" % (c["ResourceRecordSet"]["Name"], c["ResourceRecordSet"]["Type"], " | ".join(r["Value"] for r in c["ResourceRecordSet"]["ResourceRecords"]))) for c in json.loads(sys.argv[1])["Changes"]]' "$BATCH"
  fi
fi

if [[ "$GHVARS" == 1 ]]; then
  need gh dig
  gh auth status >/dev/null 2>&1 || die "Log in to GitHub first: gh auth login"
  if [[ -z "$ZONE" ]]; then
    die "No hosted zone yet - run with --apply first"
  elif ! domain_delegated "$DOMAIN" "$ZONE"; then
    warn "$DOMAIN does not point at THIS zone's four name servers yet (compare: dig +short NS $DOMAIN @1.1.1.1)."
    warn "Change them at your registrar, wait (usually under an hour, at most 48 hours), then run --connect again."
  else
    gh variable set PORTFOLIO_DOMAIN --repo "$REPO" --body "$DOMAIN"
    gh variable set PORTFOLIO_ZONE_ID --repo "$REPO" --body "$ZONE"
    gh variable set PORTFOLIO_EXTRA_DOMAINS --repo "$REPO" --body "[\"www.$DOMAIN\"]"
    log "Repository variables set on $REPO."
    owner="${GITHUB_OWNER:-ObaidAbdullah16}"
    if gh repo view "$owner/incidentscribe-ai" >/dev/null 2>&1; then
      gh variable set INCIDENTSCRIBE_ALLOWED_ORIGINS --repo "$owner/incidentscribe-ai" \
        --body "[\"https://$DOMAIN\",\"https://www.$DOMAIN\"]"
      log "incidentscribe-ai: the live demo API now only answers pages on https://$DOMAIN (takes effect at its next 'up')"
    fi
    if gh repo view "$owner/bedrock-cost-calculator" >/dev/null 2>&1; then
      gh variable set PORTFOLIO_URL --repo "$owner/bedrock-cost-calculator" --body "https://$DOMAIN"
      log "bedrock-cost-calculator: 'See the service' links to https://$DOMAIN (after its next Pages run)"
    fi
    if [[ "${AWS_ACCOUNT_TYPE:-classic}" == project ]]; then
      log "Deploying the site on https://$DOMAIN from this laptop (certificate + website records: 10-20 minutes the first time)"
      bash "$REPO_ROOT/scripts/up.sh"
      log "Then refresh the two projects that link to the domain (if they are up):"
      log "  bash _setup/projects.sh up incidentscribe   and   bash _setup/projects.sh up calculator"
    elif gh workflow run deploy.yml --repo "$REPO" >/dev/null 2>&1; then
      log "Started the portfolio Deploy workflow: https://github.com/$REPO/actions (10-20 minutes the first time)"
    else
      warn "Could not start the Deploy workflow - run it by hand: GitHub > portfolio > Actions > Deploy > Run workflow"
    fi
  fi
fi

echo
echo "Next: if the domain is used by a zone in another AWS account, copy the records to keep first:"
echo "        bash scripts/copy-dns-records.sh $DOMAIN"
echo "      Change the name servers at your registrar to the four above, wait until"
echo "      'dig +short NS $DOMAIN @1.1.1.1' shows exactly those four, then run:"
echo "        bash scripts/domain-setup.sh $DOMAIN --connect"
echo "The CAA record allows only Amazon to issue certificates; add another 'issue' value if you ever use a different CA."
