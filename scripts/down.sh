#!/usr/bin/env bash
# Take the portfolio website offline (S3 bucket, CloudFront, HTTPS certificate, A/AAAA records).
# Normally you keep it running - it costs practically nothing.
#
#   bash scripts/down.sh          # website offline; the Route 53 zone stays, so your domain,
#                                 # hello@ email forwarding and DNS keep working ($0.50/month)
#   bash scripts/down.sh --all    # also deletes the Route 53 hosted zone: the domain stops
#                                 # resolving and email stops arriving (asks you to type the domain)
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need aws terraform python3
TF="$REPO_ROOT/infra"

ALL=0
for a in "$@"; do
  case "$a" in
    --all) ALL=1 ;;
    *) die "unknown option: $a (use --all or nothing)" ;;
  esac
done

tf_init "$TF" "portfolio/terraform.tfstate"
if tf_has_resources "$TF"; then
  log "Terraform destroy (disabling a CloudFront distribution takes ~5-15 minutes)"
  tf_destroy "$TF"
else
  log "Portfolio website is not deployed"
fi

[[ "$ALL" == 1 ]] || { log "Website offline. The domain, DNS and email forwarding keep working. Start again: bash scripts/up.sh"; exit 0; }

domain="${PORTFOLIO_DOMAIN:-}"
[[ -n "$domain" ]] || { log "No PORTFOLIO_DOMAIN in _setup/config.env - no hosted zone to delete."; exit 0; }
zone="$(aws route53 list-hosted-zones-by-name --dns-name "$domain." --max-items 1 \
  --query "HostedZones[?Name=='$domain.'].Id | [0]" --output text 2>/dev/null | sed 's|/hostedzone/||; s|^None$||')"
[[ -n "$zone" ]] || { log "No Route 53 hosted zone for $domain - nothing more to delete."; exit 0; }

cat <<WARN

  --all also deletes the Route 53 hosted zone for $domain ($zone).
  After that:  the domain stops resolving, mail to @$domain stops arriving, and if you
  set it up again you get NEW name servers that you must enter at your registrar again.
  The domain registration itself (paid yearly at your registrar) is not affected.

WARN
if [[ "${CONFIRM_DOMAIN:-}" != "$domain" ]]; then
  read -r -p "Type the domain ($domain) to delete its hosted zone: " answer
  [[ "$answer" == "$domain" ]] || { echo "Cancelled - the hosted zone is kept."; exit 0; }
fi

records="$(aws route53 list-resource-record-sets --hosted-zone-id "$zone" --output json)"
# Keep a copy of every record (old project sub-domains included) so they can be restored later:
#   bash scripts/copy-dns-records.sh <domain> --from-file <backup> --apply
mkdir -p "$REPO_ROOT/../_setup/dns-backups"
backup_dir="$(cd "$REPO_ROOT/../_setup/dns-backups" && pwd)"
backup="$backup_dir/$domain-$(date +%Y%m%d-%H%M%S).json"
RECORDS="$records" python3 -c 'import json,os,sys; d=json.loads(os.environ["RECORDS"]); d["HostedZoneId"]=sys.argv[2]; json.dump(d, open(sys.argv[1],"w"), indent=1)' "$backup" "$zone"
log "Saved a copy of every record in $backup"
log "Deleting every record except NS and SOA"
batch="$(RECORDS="$records" python3 - "$domain" <<'PY'
import json, os, sys
apex = sys.argv[1].rstrip(".") + "."
sets = json.loads(os.environ["RECORDS"])["ResourceRecordSets"]
changes = [{"Action": "DELETE", "ResourceRecordSet": s} for s in sets
           if not (s["Name"] == apex and s["Type"] in ("NS", "SOA"))]
print(json.dumps({"Changes": changes}) if changes else "")
PY
)"
[[ -z "$batch" ]] || aws route53 change-resource-record-sets --hosted-zone-id "$zone" --change-batch "$batch" >/dev/null
aws route53 delete-hosted-zone --id "$zone" >/dev/null
log "Hosted zone deleted"

set_config PORTFOLIO_ZONE_ID ""
if gh_ready; then
  for v in PORTFOLIO_DOMAIN PORTFOLIO_ZONE_ID PORTFOLIO_EXTRA_DOMAINS; do
    gh variable delete "$v" --repo "${GITHUB_OWNER}/portfolio" >/dev/null 2>&1 || true
  done
  log "Removed the domain variables from the portfolio repository (its Deploy uses the CloudFront address now)"
else
  warn "Delete the repository variables PORTFOLIO_DOMAIN, PORTFOLIO_ZONE_ID, PORTFOLIO_EXTRA_DOMAINS by hand (gh not logged in)"
fi
log "Done. To bring the domain back: bash scripts/domain-setup.sh $domain --apply   (then new name servers at the registrar)"
log "      and your other records (old project sub-domains): bash scripts/copy-dns-records.sh $domain --from-file $backup --apply"
