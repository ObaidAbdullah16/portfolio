#!/usr/bin/env bash
# Copy the latest sample reports, the IncidentScribe demo page and the Bedrock
# calculator from the sibling project folders (when this repo sits in
# Projects_Demos/). Commit the result.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/.."
copy() { if [[ -f "$1" ]]; then mkdir -p "$(dirname "$2")"; cp "$1" "$2"; echo "updated ${2#"$here"/}"; else echo "skip (not found): $1"; fi; }
copy "$src/aws-bill-doctor/sample-report/report.html" "$here/site/demos/bill-doctor/report.html"
# Security baseline check (S8): before, retest and DPDP views, and the AWS Health Check bundle (S1 + S8)
copy "$src/aws-bill-doctor/sample-security-report/report.html" "$here/site/demos/security-check/report.html"
copy "$src/aws-bill-doctor/sample-security-report/retest/report.html" "$here/site/demos/security-check/retest/report.html"
copy "$src/aws-bill-doctor/sample-security-report/dpdp/report.html" "$here/site/demos/security-check/dpdp/report.html"
copy "$src/aws-bill-doctor/sample-health-check/index.html" "$here/site/demos/health-check/index.html"
copy "$src/aws-bill-doctor/sample-health-check/cost/report.html" "$here/site/demos/health-check/cost/report.html"
copy "$src/aws-bill-doctor/sample-health-check/security/report.html" "$here/site/demos/health-check/security/report.html"
# Real sandbox scan (after you run aws-bill-doctor/demo-account/run-demo.sh)
copy "$src/aws-bill-doctor/sample-security-report-real/report.html" "$here/site/demos/security-check/real/report.html"
copy "$src/restore-drill-kit/sample-report/report.html" "$here/site/demos/restore-drill/report.html"
copy "$src/incidentscribe-ai/demo/index.html" "$here/site/demos/incidentscribe/index.html"
copy "$src/serverforge/sample-report/report.html" "$here/site/demos/serverforge/report.html"
# The Bedrock Bill-Shock Calculator lives at /tools/bedrock-calculator/
for f in index.html style.css config.js prices.js calc.js app.js; do
  copy "$src/bedrock-cost-calculator/site/$f" "$here/site/tools/bedrock-calculator/$f"
done
