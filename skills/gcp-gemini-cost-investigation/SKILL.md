---
name: gcp-gemini-cost-investigation
description: Google Cloud プロジェクトのコスト調査。Gemini API のトークン使用量をモデル別・APIキー別・日別に分析し、コスト増加の原因を特定する。GCPコスト、請求、Gemini API 使用量、トークン消費について聞かれた時に使用する。Investigate Google Cloud Gemini API costs, token usage by model, API key, and day.
---

# GCP Gemini API Cost Investigation

Google Cloud プロジェクトの Gemini API コストを調査し、使用量の内訳と増加原因を特定する。

## Configuration

プロジェクト固有の設定は `config.env` に記載する（`config.env.example` をコピーして作成）。

```bash
# config.env
GCP_PROJECT_ID="your-project-id"
```

`--project=<ID>` オプションで都度上書きも可能。

## Prerequisites

- `gcloud` CLI が認証済みであること
- 対象プロジェクトへの `monitoring.timeSeries.list` 権限
- 対象プロジェクトへの `apikeys.keys.list` 権限（APIキー特定時）
- `curl` と `python3` が使用可能であること

## Investigation Procedure

### Step 1: プロジェクトと請求先の確認

```bash
gcloud billing projects describe <PROJECT_ID> --format="json"
```

### Step 2: サービス別リクエスト数の概要

Cloud Monitoring API で `serviceruntime.googleapis.com/api/request_count` を `resource.labels.service` でグループ化し、対象月のリクエスト数をサービス別に取得する。

```bash
./scripts/query_usage.sh service_summary
```

### Step 3: モデル別トークン使用量（入力）

最もコストに影響する入力トークン数をモデル別に取得する。Paid Tier 3 のメトリクスが最も網羅的。

**メトリクス**: `generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage`

```bash
./scripts/query_usage.sh token_input
```

### Step 4: モデル別トークン使用量（出力）

**メトリクス**: `generativelanguage.googleapis.com/generate_content_usage_output_token_count`

出力トークンは `thinking_enabled` ラベルで分類される。thinking=true の場合、出力トークンのコストが高い。

```bash
./scripts/query_usage.sh token_output
```

### Step 5: 日別トレンド（スパイク検出）

入力トークンを日別（`alignmentPeriod=86400s`）に集計し、異常なスパイクを特定する。

```bash
./scripts/query_usage.sh daily_input --model=<MODEL_NAME>
./scripts/query_usage.sh daily_requests
```

### Step 6: APIキー別の利用者特定

**重要**: `serviceruntime.googleapis.com/api/request_count` を集計なし（raw）で取得すると、`resource.labels.credential_id` に `apikey:<UUID>` 形式でAPIキーIDが記録されている。

APIキー名の一覧と突合して、どのキー（＝どのアプリ/ユーザー）が利用しているか特定する。

```bash
./scripts/query_usage.sh by_apikey
./scripts/query_usage.sh apikey_list
```

### Step 7: 前月比較

同じメトリクスを前月の期間で取得し、増加率を計算する。

```bash
./scripts/query_usage.sh compare_months
```

### Step 8: コスト推定

以下の料金テーブル（概算、USD / 1M トークン）でコストを推定する:

| モデル | 入力 | 出力 | 出力 (thinking) |
|--------|------|------|-----------------|
| gemini-2.5-pro | $1.25 | $5.00 | $10.00 |
| gemini-2.5-flash | $0.15 | $0.30 | $0.60 |
| gemini-2.5-flash-lite | $0.075 | $0.15 | $0.30 |

※ 料金は変更される可能性がある。最新の公式料金は https://ai.google.dev/pricing で確認すること。
※ 上記にないモデル（gemini-3.x 系など）は、同クラスのモデル料金を参考に推定する。

## Output Format

調査結果は以下を含めること:

1. **コスト内訳テーブル** — モデル別の入力/出力トークン数と推定コスト
2. **前月比較** — 増加率とトークン量の比較
3. **スパイク特定** — 異常に使用量が多い日とその規模
4. **APIキー別利用割合** — どのアプリ/キーが何%使っているか
5. **推奨アクション** — コスト削減のための具体的な提案

## Key Metrics Reference

| 目的 | メトリクス | グループ化ラベル |
|------|-----------|-----------------|
| サービス別リクエスト数 | `serviceruntime.googleapis.com/api/request_count` | `resource.labels.service` |
| 入力トークン（有料） | `generativelanguage.googleapis.com/quota/generate_content_paid_tier_3_input_token_count/usage` | `metric.labels.model` |
| 出力トークン | `generativelanguage.googleapis.com/generate_content_usage_output_token_count` | `metric.labels.model`, `metric.labels.thinking_enabled` |
| APIキー特定 | `serviceruntime.googleapis.com/api/request_count` (raw, no cross-series aggregation) | `resource.labels.credential_id` |

## Notes

- Cloud Monitoring の無料メトリクス保持期間は6週間。それ以前のデータが必要な場合は有料の保持設定が必要。
- Billing Export (BigQuery) を設定すると正確な請求額が確認できるが、APIキー別の粒度は含まれない。
- Data Access Audit Log を有効化すれば、リクエストごとの呼び出し元（サービスアカウントやユーザー）を Cloud Logging で確認できる。
- APIキー認証の場合、`credential_id` でキーは特定できるが、そのキーを使った人間の特定はアプリ側のログに依存する。
