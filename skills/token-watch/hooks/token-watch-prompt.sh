#!/bin/bash
# token-watch: UserPromptSubmit hook
# 状態ファイル(Stop hookが更新)を参照し、必要なときだけ additionalContext を注入する。
# 問題がなければ {} を返してトークンを一切消費しない。
set -u

BASE="${TOKEN_WATCH_DIR:-$HOME/.claude/token-watch}"

# 監視が無効なら即終了
[ -f "$BASE/enabled" ] || { echo '{}'; exit 0; }

# ---- チューニング可能なしきい値(環境変数で上書き可) ----
SIZE_WARN_KB="${TOKEN_WATCH_SIZE_WARN_KB:-600}"        # transcriptサイズ警告 (KB)
COOLDOWN_TURNS="${TOKEN_WATCH_COOLDOWN_TURNS:-10}"     # 提案の再表示までの最低ターン数
MIN_TURNS_FOR_SWITCH="${TOKEN_WATCH_MIN_TURNS:-6}"     # タスク切替検出を有効にする最低ターン数
VAGUE_MAX_LEN="${TOKEN_WATCH_VAGUE_MAX_LEN:-60}"       # 曖昧プロンプト判定の最大文字数

command -v jq >/dev/null 2>&1 || { echo '{}'; exit 0; }

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
prompt=$(printf '%s' "$input" | jq -r '.prompt // empty')
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
[ -n "$session_id" ] || { echo '{}'; exit 0; }

state_dir="$BASE/sessions"
state="$state_dir/$session_id.json"
ids_file="$state_dir/$session_id.ids"
mkdir -p "$state_dir"

turns=0
last=-9999
if [ -f "$state" ]; then
  turns=$(jq -r '.turns // 0' "$state" 2>/dev/null || echo 0)
  last=$(jq -r '.last_suggest_turn // -9999' "$state" 2>/dev/null || echo -9999)
fi

# 識別子パターン(共通定義から読み込み。カスタマイズは id-pattern ファイル参照)
. "$(dirname "$0")/token-watch-common.sh"

warnings=""

# ---- 1. コンテキスト肥大チェック ----
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  bytes=$(wc -c < "$transcript" | tr -d ' ')
  kb=$(( bytes / 1024 ))
  if [ "$kb" -ge "$SIZE_WARN_KB" ]; then
    warnings="${warnings}- セッションのtranscriptが約${kb}KBに達しており、コンテキストが肥大している可能性があります。\n"
  fi
fi

# ---- 2. タスク切り替え検出(識別子の乖離)----
if [ -f "$ids_file" ] && [ "$turns" -ge "$MIN_TURNS_FOR_SWITCH" ]; then
  new_ids=$(printf '%s' "$prompt" | grep -oE "$ID_RE" 2>/dev/null | sort -u || true)
  if [ -n "$new_ids" ]; then
    overlap=$(printf '%s\n' "$new_ids" | grep -Fxf "$ids_file" 2>/dev/null | head -1 || true)
    if [ -z "$overlap" ]; then
      sample=$(printf '%s\n' "$new_ids" | head -3 | tr '\n' ' ')
      warnings="${warnings}- 新しいプロンプトはこのセッションで未登場の識別子(${sample})に言及しており、無関係なタスクへの切り替えの可能性があります。\n"
    fi
  fi
fi

# ---- 3. 曖昧プロンプト検出(クールダウン対象外・軽量ヒント)----
vague_hint=""
plen=${#prompt}
if [ "$plen" -gt 0 ] && [ "$plen" -le "$VAGUE_MAX_LEN" ]; then
  if printf '%s' "$prompt" | grep -qiE '改善|直して|修正して|きれいに|リファクタ|最適化して|fix|improve|clean ?up|refactor|optimi[sz]e' \
     && ! printf '%s' "$prompt" | grep -qE "$ID_RE"; then
    vague_hint="[token-watch] このプロンプトは対象が特定されておらず、広範なコードベーススキャンを誘発する可能性があります。対象ファイル・関数・範囲を推測できない場合は、大規模な探索を始める前に対象をユーザに確認してください。"
  fi
fi

# ---- 出力の組み立て ----
context=""

if [ -n "$warnings" ] && [ $(( turns - last )) -ge "$COOLDOWN_TURNS" ]; then
  context="[token-watch] 以下の兆候を検出しました:\n${warnings}今回の応答の本題を終えたあと、最後に1〜2行だけで以下をユーザに簡潔に提案してください: 無関係なタスクに切り替える場合は /clear (必要なら事前に /rename)、このセッションを続けて診断したい場合は token-review スキルの実行。提案は控えめに、1度だけ述べること。"
  # クールダウン更新
  if [ -f "$state" ]; then
    tmp=$(mktemp)
    jq --argjson t "$turns" '.last_suggest_turn = $t' "$state" > "$tmp" 2>/dev/null && mv "$tmp" "$state" || rm -f "$tmp"
  else
    printf '{"turns": %s, "last_suggest_turn": %s}\n' "$turns" "$turns" > "$state"
  fi
fi

if [ -n "$vague_hint" ]; then
  if [ -n "$context" ]; then
    context="${context}\n\n${vague_hint}"
  else
    context="$vague_hint"
  fi
fi

if [ -n "$context" ]; then
  # \n をリテラル改行に展開して JSON へ
  printf '%b' "$context" | jq -Rs '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: .}}'
else
  echo '{}'
fi
exit 0
