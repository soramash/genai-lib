# gcp-gemini-cost-investigation

An [Agent Skill](https://agentskills.io) for investigating Google Cloud Gemini API costs using Cloud Monitoring metrics.

This skill helps AI agents (Kiro, etc.) analyze Gemini API usage and costs by:

- Breaking down token consumption by model
- Identifying which API keys are responsible for the most usage
- Detecting daily usage spikes
- Comparing month-over-month trends
- Estimating costs based on public pricing

## Installation

Copy the skill folder into your project:

```bash
cp -r gcp-gemini-cost-investigation /path/to/your/project/.kiro/skills/
```

Then configure your defaults in `config.env`:

```bash
cd /path/to/your/project/.kiro/skills/gcp-gemini-cost-investigation
cp config.env.example config.env
# Edit config.env with your project ID
```

## Configuration

Create `config.env` (not committed to git) with your defaults:

```bash
# Google Cloud Project ID to investigate
GCP_PROJECT_ID="your-project-id"

# (Optional) Billing Account ID
GCP_BILLING_ACCOUNT=""
```

All values can be overridden via command-line options.

## Prerequisites

- `gcloud` CLI installed and authenticated
- Permission: `monitoring.timeSeries.list` on the target project
- Permission: `apikeys.keys.list` for API key identification
- `curl` and `python3` available in PATH

## Usage

### Via AI Agent

Ask your agent naturally:

- "GCP のコスト調べて" / "Investigate GCP costs"
- "Gemini API の使用量を分析して" / "Analyze Gemini API usage"
- "先月のトークン消費量をモデル別に見せて" / "Show token usage by model for last month"

The skill activates automatically based on the description in `SKILL.md`.

### Via Script Directly

```bash
# Show help
./scripts/query_usage.sh help

# Service-level request summary
./scripts/query_usage.sh service_summary

# Input tokens by model
./scripts/query_usage.sh token_input

# Output tokens by model (with thinking mode breakdown)
./scripts/query_usage.sh token_output

# Daily input token trend (spike detection)
./scripts/query_usage.sh daily_input --model=gemini-2.5-pro

# Daily request count by model
./scripts/query_usage.sh daily_requests

# Requests by API key (identifies who/what is using the API)
./scripts/query_usage.sh by_apikey

# List all API keys in the project
./scripts/query_usage.sh apikey_list

# Month-over-month comparison
./scripts/query_usage.sh compare_months
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project=<ID>` | Google Cloud Project ID | Value from `config.env` |
| `--year=<YYYY>` | Target year | Previous month's year |
| `--month=<MM>` | Target month | Previous month |
| `--model=<name>` | Model name (for `daily_input`) | `gemini-2.5-pro` |

## What It Can Identify

| Question | Method |
|----------|--------|
| Which service costs the most? | `serviceruntime` request count by service |
| Which model uses the most tokens? | Paid tier input/output token metrics |
| Who is making the calls? | `credential_id` in raw metrics → API key name |
| When did usage spike? | Daily aggregation of token metrics |
| Is usage growing? | Month-over-month comparison |

## Limitations

- **Billing Export not required** — works directly with Cloud Monitoring metrics
- **API key level granularity** — can identify which API key, but not which end-user behind it
- **Data Access Audit Logs** — if enabled separately, can provide caller identity beyond API keys
- **Metric retention** — Cloud Monitoring free tier retains data for 6 weeks
- **Pricing estimates** — based on public pricing; actual bills may differ due to discounts or committed use

## License

MIT
