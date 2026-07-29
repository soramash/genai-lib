#!/bin/bash
# token-watch: statusline
# コンテキスト使用率を常時表示(トークン消費ゼロの可視化レイヤー)
input=$(cat)

model=$(printf '%s' "$input" | jq -r '.model.display_name // "Claude"')
pct=$(printf '%s' "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
cost=$(printf '%s' "$input" | jq -r '.cost.total_cost_usd // 0')
watch="OFF"
[ -f "${TOKEN_WATCH_DIR:-$HOME/.claude/token-watch}/enabled" ] && watch="ON"

# 10文字のプログレスバー
filled=$(( pct / 10 )); [ "$filled" -gt 10 ] && filled=10
bar=""
for ((i=0; i<10; i++)); do
  if [ "$i" -lt "$filled" ]; then bar+="▓"; else bar+="░"; fi
done

# 色: <50% 緑 / <80% 黄 / それ以上 赤
if [ "$pct" -lt 50 ]; then c="\033[32m"
elif [ "$pct" -lt 80 ]; then c="\033[33m"
else c="\033[31m"; fi
r="\033[0m"

cost_fmt=$(printf '%.2f' "$cost" 2>/dev/null || echo "$cost")
printf "[%s] ${c}%s %s%%${r} ctx | \$%s | watch:%s" "$model" "$bar" "$pct" "$cost_fmt" "$watch"
