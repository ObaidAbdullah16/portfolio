#!/usr/bin/env bash
# Copy DNS records from the domain's OLD hosted zone (in another AWS account) into the NEW zone
# in this account, before you point the domain's name servers at the new zone. Old project
# sub-domains then keep working through the switch; the old website and old email do not move.
#
#   bash scripts/copy-dns-records.sh example.com                  # dry run: lists every old record + KEEP/SKIP
#   bash scripts/copy-dns-records.sh example.com --apply          # copies the KEEP records into the new zone
#   ... --from-profile old        AWS CLI profile of the old account (default: OLD_AWS_PROFILE in config.env, or "old")
#   ... --from-zone Z123          the old zone's ID, if the old account has more than one zone for the domain
#   ... --skip app.example.com  do not copy this name (repeat for more)
#   ... --keep www.example.com  copy this name although the rules below would skip it (repeat for more)
#   ... --from-file F.json        restore from a backup that 'down portfolio --all' saved (no old account needed)
#
# Rules (the new site and email are set up by domain-setup.sh and Terraform):
#   SKIP  the top of the domain (old website, old email: A/AAAA/MX/TXT/CAA...), NS and SOA
#   SKIP  www.<domain> (old website) and _xxx.<domain> / _xxx.www.<domain> (old certificate checks, _dmarc)
#   SKIP  *._domainkey.<domain> (DKIM keys of the old email)
#   KEEP  every other sub-domain (old projects), including their own _xxx certificate-check records
#         so their certificates can still renew.
# Health checks belong to the old account and cannot be referenced from here: they are dropped (with a warning).
# Read-only on the old account. Safe to run again: records are upserted.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DOMAIN="${1:?usage: copy-dns-records.sh <domain> [--apply] [--from-profile P] [--from-zone ID] [--from-file F] [--skip NAME] [--keep NAME]}"
shift
APPLY=0 FROM_PROFILE="${OLD_AWS_PROFILE:-old}" FROM_ZONE="" FROM_FILE="" SKIPS="" KEEPS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --from-profile) FROM_PROFILE="${2:?}"; shift ;;
    --from-zone) FROM_ZONE="${2:?}"; shift ;;
    --from-file) FROM_FILE="${2:?}"; shift ;;
    --skip) SKIPS="$SKIPS ${2:?}"; shift ;;
    --keep) KEEPS="$KEEPS ${2:?}"; shift ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done
need aws python3

new_acct="$(aws_account_id)" || die "Not logged in to the new account: bash _setup/aws-login.sh"
if [[ -n "$FROM_FILE" ]]; then
  [[ -f "$FROM_FILE" ]] || die "No such backup file: $FROM_FILE (they are in _setup/dns-backups/)"
else
  aws sts get-caller-identity --profile "$FROM_PROFILE" >/dev/null 2>&1 \
    || die "Profile '$FROM_PROFILE' (old account) is not logged in. Run: bash _setup/aws-login.sh --profile $FROM_PROFILE"
  old_acct="$(aws sts get-caller-identity --profile "$FROM_PROFILE" --query Account --output text)"
  [[ "$old_acct" != "$new_acct" ]] || die "Profile '$FROM_PROFILE' is the same account as your main profile ($new_acct). It must be the OLD account."
fi

zones_named() { # zones_named <profile or empty>
  local p=(); [[ -n "$1" ]] && p=(--profile "$1")
  aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN." "${p[@]}" \
    --query "HostedZones[?Name=='$DOMAIN.' && Config.PrivateZone==\`false\`].Id" --output text | tr '\t' '\n' | sed 's|/hostedzone/||' | grep -v '^None$' || true
}
if [[ -n "$FROM_FILE" ]]; then
  FROM_ZONE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("HostedZoneId",""))' "$FROM_FILE")"
elif [[ -z "$FROM_ZONE" ]]; then
  mapfile -t old_zones < <(zones_named "$FROM_PROFILE")
  [[ ${#old_zones[@]} -gt 0 ]] || die "No public zone for $DOMAIN in the old account ($old_acct). Nothing to copy."
  [[ ${#old_zones[@]} -eq 1 ]] || die "The old account has ${#old_zones[@]} zones for $DOMAIN (${old_zones[*]}). Pick the one the domain uses now with --from-zone (dig +short NS $DOMAIN shows its name servers)."
  FROM_ZONE="${old_zones[0]}"
fi
NEW_ZONE="${PORTFOLIO_ZONE_ID:-}"
if [[ -z "$NEW_ZONE" ]]; then
  mapfile -t new_zones < <(zones_named "")
  NEW_ZONE="${new_zones[0]:-}"
fi
[[ -n "$NEW_ZONE" ]] || die "No zone for $DOMAIN in this account yet. Create it first: bash scripts/domain-setup.sh $DOMAIN --apply"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
if [[ -n "$FROM_FILE" ]]; then
  log "Backup $FROM_FILE -> zone $NEW_ZONE (account $new_acct)"
  cp "$FROM_FILE" "$work/old.json"
else
  log "Old zone $FROM_ZONE (account $old_acct, profile $FROM_PROFILE) -> new zone $NEW_ZONE (account $new_acct)"
  aws route53 list-resource-record-sets --hosted-zone-id "$FROM_ZONE" --profile "$FROM_PROFILE" --output json > "$work/old.json"
fi

DOMAIN="$DOMAIN" FROM_ZONE="$FROM_ZONE" NEW_ZONE="$NEW_ZONE" SKIPS="$SKIPS" KEEPS="$KEEPS" \
python3 - "$work/old.json" "$work/batch.json" <<'PY'
import json, os, sys
src, out = sys.argv[1], sys.argv[2]
d = os.environ["DOMAIN"].rstrip(".").lower() + "."
norm = lambda n: (n.rstrip(".").lower() + ".").replace("\\052", "*")
skips = {norm(x) for x in os.environ["SKIPS"].split()}
keeps = {norm(x) for x in os.environ["KEEPS"].split()}
old_zone, new_zone = os.environ["FROM_ZONE"], os.environ["NEW_ZONE"]

def decide(name, rtype):
    if name in skips:
        return False, "you asked to skip it"
    if name in keeps:
        return True, "you asked to keep it"
    if name == d:
        return False, "top of the domain (old website/email; the new setup makes its own)" if rtype not in ("NS", "SOA") else "made by Route 53"
    if name == "www." + d:
        return False, "old website"
    first, _, rest = name.partition(".")
    if first.startswith("_") and rest in (d, "www." + d):
        return False, "old website certificate check / old email setting"
    if "._domainkey." in "." + name:
        return False, "old email (DKIM key)"
    return True, "old project sub-domain"

def value(s):
    if "AliasTarget" in s:
        return "ALIAS -> " + s["AliasTarget"]["DNSName"]
    vals = [r["Value"] for r in s.get("ResourceRecords", [])]
    v = " | ".join(vals)
    return v if len(v) < 70 else v[:67] + "..."

sets = json.load(open(src)).get("ResourceRecordSets", [])
changes, rows, warnings = [], [], []
for s in sets:
    name = norm(s["Name"])
    keep, why = decide(name, s["Type"])
    rows.append(("KEEP" if keep else "skip", s["Name"].replace("\\052", "*"), s["Type"], value(s), why))
    if not keep:
        continue
    r = {k: v for k, v in s.items() if k not in ("HealthCheckId", "TrafficPolicyInstanceId")}
    if "HealthCheckId" in s:
        warnings.append(f"{s['Name']} {s['Type']}: its health check stays in the old account and is not copied")
    if "TrafficPolicyInstanceId" in s:
        warnings.append(f"{s['Name']} {s['Type']}: managed by a Route 53 traffic policy in the old account - recreate it by hand")
        continue
    at = r.get("AliasTarget")
    if at and at.get("HostedZoneId") == old_zone:
        r["AliasTarget"] = dict(at, HostedZoneId=new_zone)   # alias to another record of the same zone
    changes.append({"Action": "UPSERT", "ResourceRecordSet": r})

print(f"{'':4} {'NAME':40} {'TYPE':5} {'VALUE':45} WHY")
for k, n, t, v, why in sorted(rows, key=lambda x: (x[0] != "KEEP", x[1], x[2])):
    print(f"{k:4} {n[:40]:40} {t:5} {v[:45]:45} {why}")
for w in warnings:
    print("  ! " + w)
json.dump({"Comment": "copied from the old zone by copy-dns-records.sh", "Changes": changes} if changes else {}, open(out, "w"))
print(f"\n{len(changes)} record set(s) to copy, {len(rows) - len(changes)} skipped.")
PY

# The new site cannot use the domain while a CloudFront distribution in the old account still lists it
# (CloudFront answers CNAMEAlreadyExists). Read-only check, so you know what to free before --connect.
[[ -n "$FROM_FILE" ]] || cf="$(aws cloudfront list-distributions --profile "$FROM_PROFILE" --output text \
  --query "DistributionList.Items[?Aliases.Quantity > \`0\` && (contains(Aliases.Items, '$DOMAIN') || contains(Aliases.Items, 'www.$DOMAIN'))].[Id, DomainName]" \
  2>/dev/null | grep -v '^None$' || true)"
if [[ -n "${cf:-}" ]]; then
  echo
  warn "The old account's CloudFront still uses $DOMAIN / www.$DOMAIN (the old website):"
  sed 's/^/    /' <<<"$cf"
  warn "Before 'domain-setup.sh $DOMAIN --connect': old account > CloudFront > that distribution > Edit >"
  warn "remove $DOMAIN and www.$DOMAIN from 'Alternate domain names' > Save. (Disabling alone is not enough.)"
fi

if [[ ! -s "$work/batch.json" || "$(cat "$work/batch.json")" == "{}" ]]; then
  log "Nothing to copy."
  exit 0
fi
if [[ "$APPLY" != 1 ]]; then
  log "Dry run - nothing changed. Check the KEEP lines; use --skip/--keep to adjust, then add --apply."
  exit 0
fi
status="$(aws route53 change-resource-record-sets --hosted-zone-id "$NEW_ZONE" --change-batch "file://$work/batch.json" \
  --query ChangeInfo.Status --output text)"
log "Copied into the new zone (status: $status). Check one before switching the name servers, e.g.:"
ns="$(aws route53 get-hosted-zone --id "$NEW_ZONE" --query 'DelegationSet.NameServers[0]' --output text)"
first="$(python3 -c 'import json,sys; c=json.load(open(sys.argv[1]))["Changes"][0]["ResourceRecordSet"]; print(c["Name"], c["Type"])' "$work/batch.json")"
echo "  dig +short ${first% *} ${first#* } @$ns"
