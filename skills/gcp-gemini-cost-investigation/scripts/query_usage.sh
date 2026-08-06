#!/bin/bash
# GCP Gemini API Cost Investigation Script
# Usage: ./query_usage.sh <command> [options]
#
# Commands:
#   service_summary   - Request count by service
#   token_input       - Input token count by model
#   token_output      - Output token count by model (with thinking breakdown)
#   daily_input       - Daily input token trend (spike detection)
#   daily_requests    - Daily request count by model
#   by_apikey         - Request count by API key
#   apikey_list       - List all API keys in the project
#   compare_months    - Month-over-month comparison
#   help              - Show this help
#
# Options:
#   --project=<ID>    Project ID (default: from config.env)
#   --year=<YYYY>     Target year (default: previous month's year)
#   --month=<MM>      Target month (default: previous month)
#   --model=<name>    Model name (for daily_input, default: gemini-2.5-pro)

set -euo pipefail

# --- Resolve script directory ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# --- Load config ---
PROJECT_ID=""
if [ -f "${SKILL_DIR}/config.env" ]; then
  # shellcheck source=/dev/null
  source "${SKILL_DIR}/config.env"
  PROJECT_ID="${GCP_PROJECT_ID:-}"
fi

# --- Defaults ---
YEAR=$(date -v-1m +%Y 2>/dev/null || date -d "last month" +%Y)
MONTH=$(date -v-1m +%m 2>/dev/null || date -d "last month" +%m)
MODEL=""

# --- Parse arguments ---
COMMAND="${1:-help}"
shift || true

for arg in "$@"; do
  case "$arg" in
    --project=*) PROJECT_ID="${arg#*=}" ;;
    --year=*) YEAR="${arg#*=}" ;;
    --month=*) MONTH="${arg#*=}" ;;
    --model=*) MODEL="${arg#*=}" ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# --- Validate project ID (skip for help) ---
if [ -z "$PROJECT_ID" ] && [ "$COMMAND" != "help" ] && [ "$COMMAND" != "--help" ] && [ "$COMMAND" != "-h" ]; then
  echo "Error: Project ID is required."
  echo ""
  echo "Set it in one of these ways:"
  echo "  1. Create config.env with GCP_PROJECT_ID=\"your-project-id\""
  echo "  2. Pass --project=your-project-id"
  exit 1
fi

# --- Calculate time intervals ---
START_TIME="${YEAR}-${MONTH}-01T00:00:00Z"
if [ "$MONTH" = "12" ]; then
  END_TIME="$((YEAR + 1))-01-01T00:00:00Z"
else
  END_TIME="${YEAR}-$(printf '%02d' $((10#$MONTH + 1)))-01T00:00:00Z"
fi

# Previous month calculation
if [ "$MONTH" = "01" ]; then
  PREV_YEAR=$((YEAR - 1))
  PREV_MONTH="12"
else
  PREV_YEAR="$YEAR"
  PREV_MONTH=$(printf '%02d' $((10#$MONTH - 1)))
fi
PREV_START_TIME="${PREV_YEAR}-${PREV_MONTH}-01T00:00:00Z"
PREV_END_TIME="${START_TIME}"

# --- Get auth token ---
get_token() {
  gcloud auth print-access-token 2>/dev/null
}

# --- Query Cloud Monitoring API (with aggregation) ---
query_monitoring() {
  local filter="$1"
  local start="$2"
  local end="$3"
  local alignment_period="${4:-2592000s}"
  local aligner="${5:-ALIGN_SUM}"
  local reducer="${6:-REDUCE_SUM}"
  local group_by="${7:-}"

  local token
  token=$(get_token)

  local url="https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/timeSeries"
  local encoded_filter
  encoded_filter=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${filter}'))")
  local params="filter=${encoded_filter}&interval.startTime=${start}&interval.endTime=${end}&aggregation.alignmentPeriod=${alignment_period}&aggregation.perSeriesAligner=${aligner}"

  if [ -n "$reducer" ]; then
    params="${params}&aggregation.crossSeriesReducer=${reducer}"
  fi

  if [ -n "$group_by" ]; then
    params="${params}&aggregation.groupByFields=${group_by}"
  fi

  curl -s -H "Authorization: Bearer ${token}" "${url}?${params}"
}

# --- Query Cloud Monitoring API (raw, no cross-series aggregation) ---
query_monitoring_raw() {
  local filter="$1"
  local start="$2"
  local end="$3"
  local alignment_period="${4:-2592000s}"
  local aligner="${5:-ALIGN_SUM}"

  local token
  token=$(get_token)

  local url="https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/timeSeries"
  local encoded_filter
  encoded_filter=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${filter}'))")
  local params="filter=${encoded_filter}&interval.startTime=${start}&interval.endTime=${end}&aggregation.alignmentPeriod=${alignment_period}&aggregation.perSeriesAligner=${aligner}"

  curl -s -H "Authorization: Bearer ${token}" "${url}?${params}"
}

# ============================================================
# Commands
# ============================================================

cmd_service_summary() {
  echo "=== Request Count by Service (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo "Period: ${START_TIME} ~ ${END_TIME}"
  echo ""

  query_monitoring \
    "metric.type=\"serviceruntime.googleapis.com/api/request_count\"" \
    "$START_TIME" "$END_TIME" \
    "2592000s" "ALIGN_SUM" "REDUCE_SUM" \
    "resource.labels.service" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found')
    sys.exit(0)
results = []
for ts in ts_list:
    svc = ts.get('resource', {}).get('labels', {}).get('service', 'unknown')
    points = ts.get('points', [])
    total = sum(int(p.get('value', {}).get('int64Value', 0)) for p in points)
    results.append((svc, total))
results.sort(key=lambda x: -x[1])
for svc, count in results:
    print(f'  {svc}: {count:,} requests')
print(f'\n  TOTAL: {sum(x[1] for x in results):,} requests')
"
}

cmd_token_input() {
  echo "=== Input Token Count by Model - Paid Tier 3 (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  query_monitoring \
    "metric.type=\"generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage\"" \
    "$START_TIME" "$END_TIME" \
    "2592000s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found')
    print('  (Ensure generativelanguage.googleapis.com is enabled and has paid tier usage)')
    sys.exit(0)
results = []
for ts in ts_list:
    model = ts.get('metric', {}).get('labels', {}).get('model', 'unknown')
    points = ts.get('points', [])
    total = sum(int(p.get('value', {}).get('int64Value', 0)) for p in points)
    results.append((model, total))
results.sort(key=lambda x: -x[1])
for model, count in results:
    print(f'  {model}: {count:,} tokens')
if results:
    print(f'\n  TOTAL: {sum(x[1] for x in results):,} tokens')
"
}

cmd_token_output() {
  echo "=== Output Token Count by Model (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  query_monitoring \
    "metric.type=\"generativelanguage.googleapis.com/generate_content_usage_output_token_count\"" \
    "$START_TIME" "$END_TIME" \
    "2592000s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model,metric.labels.thinking_enabled" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found')
    sys.exit(0)
results = []
for ts in ts_list:
    model = ts.get('metric', {}).get('labels', {}).get('model', 'unknown')
    thinking = ts.get('metric', {}).get('labels', {}).get('thinking_enabled', 'N/A')
    points = ts.get('points', [])
    total = sum(int(p.get('value', {}).get('int64Value', 0)) for p in points)
    results.append((model, thinking, total))
results.sort(key=lambda x: -x[2])
for model, thinking, count in results:
    print(f'  {model} (thinking={thinking}): {count:,} tokens')
if results:
    print(f'\n  TOTAL: {sum(x[2] for x in results):,} tokens')
"
}

cmd_daily_input() {
  local target_model="${MODEL:-gemini-2.5-pro}"
  echo "=== ${target_model} Daily Input Tokens (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  local filter="metric.type=\"generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage\" AND metric.labels.model=\"${target_model}\""

  query_monitoring \
    "$filter" \
    "$START_TIME" "$END_TIME" \
    "86400s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found for this model')
    print('  Try: --model=gemini-2.5-flash or check available models with token_input command')
    sys.exit(0)
for ts in ts_list:
    points = ts.get('points', [])
    points.sort(key=lambda p: p['interval']['startTime'])
    max_val = max((int(p.get('value', {}).get('int64Value', 0)) for p in points), default=1)
    scale = max(max_val // 50, 1)
    for p in points:
        date = p['interval']['startTime'][:10]
        val = int(p.get('value', {}).get('int64Value', 0))
        bar = chr(9608) * (val // scale)
        print(f'  {date}: {val:>15,} tokens  {bar}')
"
}

cmd_daily_requests() {
  echo "=== Daily Request Count by Model (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  query_monitoring \
    "metric.type=\"generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_requests/usage\"" \
    "$START_TIME" "$END_TIME" \
    "86400s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found')
    sys.exit(0)
models = {}
for ts in ts_list:
    model = ts.get('metric', {}).get('labels', {}).get('model', 'unknown')
    points = ts.get('points', [])
    for p in points:
        date = p['interval']['startTime'][:10]
        val = int(p.get('value', {}).get('int64Value', 0))
        if date not in models:
            models[date] = {}
        models[date][model] = models[date].get(model, 0) + val

# Top 3 models by total
model_totals = {}
for date_data in models.values():
    for m, v in date_data.items():
        model_totals[m] = model_totals.get(m, 0) + v
top_models = sorted(model_totals.keys(), key=lambda m: -model_totals[m])[:3]

header = f'{\"Date\":<12}' + ''.join(f'{m:>20}' for m in top_models)
print(header)
print('-' * len(header))
for date in sorted(models.keys()):
    row = f'{date:<12}'
    for m in top_models:
        row += f'{models[date].get(m, 0):>20,}'
    print(row)
"
}

cmd_by_apikey() {
  echo "=== Requests by API Key (${YEAR}/${MONTH}) ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  # Get API key name mapping
  local key_map
  key_map=$(gcloud services api-keys list --project="${PROJECT_ID}" \
    --format="csv[no-heading](uid,displayName)" 2>/dev/null || echo "")

  # Get raw data with credential_id
  query_monitoring_raw \
    "metric.type=\"serviceruntime.googleapis.com/api/request_count\" AND resource.labels.service=\"generativelanguage.googleapis.com\"" \
    "$START_TIME" "$END_TIME" \
    "2592000s" "ALIGN_SUM" \
  | python3 -c "
import json, sys

# Load API key name mapping
key_names = {}
key_map_raw = sys.stdin.read()

# The input contains the key_map followed by the JSON - we need a different approach
# Actually we receive JSON from curl via pipe
import os
key_map_lines = '''${key_map}'''
for line in key_map_lines.strip().split('\n'):
    if ',' in line:
        uid, name = line.split(',', 1)
        key_names[f'apikey:{uid}'] = name

# Re-read from the actual pipe - this script receives JSON from query_monitoring_raw
# We need to parse the JSON that was piped in
import io
# The JSON comes from stdin via the pipe
data = json.loads(key_map_raw)

ts_list = data.get('timeSeries', [])
if not ts_list:
    print('  No data found')
    print('  (Ensure generativelanguage.googleapis.com has been used in this period)')
    sys.exit(0)

credentials = {}
for ts in ts_list:
    cred = ts.get('resource', {}).get('labels', {}).get('credential_id', 'unknown')
    points = ts.get('points', [])
    total = sum(int(p.get('value', {}).get('int64Value', 0)) for p in points)
    credentials[cred] = credentials.get(cred, 0) + total

total_all = sum(credentials.values())
results = sorted(credentials.items(), key=lambda x: -x[1])

for cred, count in results:
    name = key_names.get(cred, cred)
    pct = (count / total_all * 100) if total_all > 0 else 0
    print(f'  {name:<45} {count:>8,} reqs  ({pct:.1f}%)')

print(f'\n  {\"TOTAL\":<45} {total_all:>8,} reqs')
"
}

cmd_apikey_list() {
  echo "=== API Keys ==="
  echo "Project: ${PROJECT_ID}"
  echo ""
  gcloud services api-keys list --project="${PROJECT_ID}" \
    --format="table(uid,displayName,createTime)"
}

cmd_compare_months() {
  echo "=== Month-over-Month Comparison: ${PREV_YEAR}/${PREV_MONTH} vs ${YEAR}/${MONTH} ==="
  echo "Project: ${PROJECT_ID}"
  echo ""

  # Current month
  local current
  current=$(query_monitoring \
    "metric.type=\"generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage\"" \
    "$START_TIME" "$END_TIME" \
    "2592000s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model")

  # Previous month
  local previous
  previous=$(query_monitoring \
    "metric.type=\"generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage\"" \
    "$PREV_START_TIME" "$PREV_END_TIME" \
    "2592000s" "ALIGN_SUM" "REDUCE_SUM" \
    "metric.labels.model")

  python3 -c "
import json, sys

current = json.loads('''${current}''')
previous = json.loads('''${previous}''')

def extract(data):
    result = {}
    for ts in data.get('timeSeries', []):
        model = ts.get('metric', {}).get('labels', {}).get('model', 'unknown')
        points = ts.get('points', [])
        total = sum(int(p.get('value', {}).get('int64Value', 0)) for p in points)
        result[model] = total
    return result

curr = extract(current)
prev = extract(previous)

if not curr and not prev:
    print('  No data found for either month')
    sys.exit(0)

all_models = sorted(set(list(curr.keys()) + list(prev.keys())),
                    key=lambda m: -(curr.get(m, 0)))

print(f'{\"Model\":<25} {\"Previous\":>18} {\"Current\":>18} {\"Change\":>10}')
print('-' * 75)
for model in all_models:
    c = curr.get(model, 0)
    p = prev.get(model, 0)
    if p > 0:
        change = ((c - p) / p) * 100
        change_str = f'{change:+.0f}%'
    elif c > 0:
        change_str = 'NEW'
    else:
        change_str = '-'
    print(f'  {model:<23} {p:>16,} {c:>16,}   {change_str:>8}')

total_prev = sum(prev.values())
total_curr = sum(curr.values())
if total_prev > 0:
    total_change = ((total_curr - total_prev) / total_prev) * 100
    total_change_str = f'{total_change:+.0f}%'
else:
    total_change_str = 'N/A'
print('-' * 75)
print(f'  {\"TOTAL\":<23} {total_prev:>16,} {total_curr:>16,}   {total_change_str:>8}')
"
}

cmd_help() {
  cat << 'HELP'
GCP Gemini API Cost Investigation Script

Usage: query_usage.sh <command> [options]

Commands:
  service_summary   Request count by service
  token_input       Input token count by model (paid tier)
  token_output      Output token count by model (with thinking breakdown)
  daily_input       Daily input token trend (spike detection)
  daily_requests    Daily request count by model
  by_apikey         Request count by API key (identifies callers)
  apikey_list       List all API keys in the project
  compare_months    Month-over-month comparison
  help              Show this help

Options:
  --project=<ID>    Project ID (default: from config.env)
  --year=<YYYY>     Target year (default: previous month's year)
  --month=<MM>      Target month (default: previous month)
  --model=<name>    Model name for daily_input (default: gemini-2.5-pro)

Examples:
  ./query_usage.sh service_summary
  ./query_usage.sh token_input --project=my-project --year=2026 --month=07
  ./query_usage.sh daily_input --model=gemini-2.5-flash
  ./query_usage.sh by_apikey
  ./query_usage.sh compare_months
HELP
}

# ============================================================
# Main
# ============================================================
case "$COMMAND" in
  service_summary) cmd_service_summary ;;
  token_input) cmd_token_input ;;
  token_output) cmd_token_output ;;
  daily_input) cmd_daily_input ;;
  daily_requests) cmd_daily_requests ;;
  by_apikey) cmd_by_apikey ;;
  apikey_list) cmd_apikey_list ;;
  compare_months) cmd_compare_months ;;
  help|--help|-h) cmd_help ;;
  *) echo "Unknown command: $COMMAND"; echo ""; cmd_help; exit 1 ;;
esac
