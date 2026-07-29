---
description: token-watch(トークン浪費監視hook)のON/OFF切り替えと状態確認
allowed-tools: Bash(mkdir:*), Bash(touch:*), Bash(rm:*), Bash(ls:*), Bash(test:*), Bash(cat:*)
---

引数: $ARGUMENTS

token-watch の監視状態を操作してください。フラグファイルは `~/.claude/token-watch/enabled` です。

- 引数が `on` の場合: `mkdir -p ~/.claude/token-watch && touch ~/.claude/token-watch/enabled` を実行し、「token-watch を有効にしました」と報告する。
- 引数が `off` の場合: `rm -f ~/.claude/token-watch/enabled` を実行し、「token-watch を無効にしました」と報告する。
- 引数が `status` または空の場合: フラグファイルの有無を確認し、現在の状態(ON/OFF)としきい値(環境変数 TOKEN_WATCH_SIZE_WARN_KB / TOKEN_WATCH_COOLDOWN_TURNS が未設定ならデフォルト 600KB / 10ターン)を1〜2行で報告する。

報告は簡潔に。余計な説明は不要です。
