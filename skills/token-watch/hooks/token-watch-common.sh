#!/bin/bash
# token-watch: 共通定義
# 識別子パターン(ID_RE)を一元管理する。両hookからsourceされる。
#
# 優先順位:
#   1. 環境変数 TOKEN_WATCH_ID_RE
#   2. ファイル ${TOKEN_WATCH_DIR:-~/.claude/token-watch}/id-pattern (1行のERE)
#   3. 既定値
#
# カスタマイズ例(JIRAプロジェクトキーを自社のものに限定したい場合):
#   echo '(PROJ|INFRA)-[0-9]+|[A-Za-z0-9_./-]+\.(ts|py|go|tf|md)' \
#     > ~/.claude/token-watch/id-pattern

TW_BASE="${TOKEN_WATCH_DIR:-$HOME/.claude/token-watch}"

TW_DEFAULT_ID_RE='sc-[0-9]+|[A-Z][A-Z0-9]+-[0-9]+|[A-Za-z0-9_./-]+\.(ts|tsx|js|jsx|py|go|rb|java|sh|bash|zsh|yaml|yml|json|toml|tf|md|sql|swift|kt|rs|c|cc|cpp|h|hpp|css|scss|html|vue|proto)'

if [ -n "${TOKEN_WATCH_ID_RE:-}" ]; then
  ID_RE="$TOKEN_WATCH_ID_RE"
elif [ -f "$TW_BASE/id-pattern" ]; then
  ID_RE=$(head -1 "$TW_BASE/id-pattern")
  # 空ファイルや空行なら既定値にフォールバック
  [ -n "$ID_RE" ] || ID_RE="$TW_DEFAULT_ID_RE"
else
  ID_RE="$TW_DEFAULT_ID_RE"
fi
