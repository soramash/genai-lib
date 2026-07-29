#!/bin/bash
# token-watch: Stop hook
# 各レスポンス後にtranscriptを分析して状態ファイルを更新するだけ。
# stdoutに判定は出さない = トークン消費ゼロ。通知は次のUserPromptSubmitが行う。
set -u

BASE="${TOKEN_WATCH_DIR:-$HOME/.claude/token-watch}"
[ -f "$BASE/enabled" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

MAX_IDS="${TOKEN_WATCH_MAX_IDS:-800}"   # 保持する識別子の上限

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
[ -n "$session_id" ] || exit 0
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

state_dir="$BASE/sessions"
mkdir -p "$state_dir"
state="$state_dir/$session_id.json"
ids_file="$state_dir/$session_id.ids"

# ターン数(userタイプ行の数。tool_resultも含むため実ターン数より多めに出るが、
# クールダウンの単調増加カウンタとしては問題ない)
turns=$(grep -c '"type":"user"' "$transcript" 2>/dev/null || echo 0)
bytes=$(wc -c < "$transcript" | tr -d ' ')

# セッション中に登場した識別子(ファイルパス・チケットID)を抽出。
# Claudeがツールで触れたファイルも含まれるため、タスク切替判定の母集合として都合が良い。
# 識別子パターンは共通定義から読み込み(カスタマイズは id-pattern ファイル参照)
. "$(dirname "$0")/token-watch-common.sh"
tmp_ids=$(mktemp)
grep -oE "$ID_RE" "$transcript" 2>/dev/null | sort -u | head -n "$MAX_IDS" > "$tmp_ids" || true
mv "$tmp_ids" "$ids_file"

# 状態更新(last_suggest_turnは保持)
last=-9999
if [ -f "$state" ]; then
  last=$(jq -r '.last_suggest_turn // -9999' "$state" 2>/dev/null || echo -9999)
fi
printf '{"turns": %s, "transcript_bytes": %s, "last_suggest_turn": %s}\n' \
  "${turns:-0}" "${bytes:-0}" "$last" > "$state"

# 古いセッションファイルの掃除(30日超)
find "$state_dir" -type f -mtime +30 -delete 2>/dev/null || true

exit 0
