# token-watch — Claude Code トークン浪費監視ツールキット

毎プロンプトでトークン浪費の兆候をローカルヒューリスティック(トークン消費ゼロ)で検査し、
必要なときだけ Claude に警告を注入して `token-review` スキルの利用を提案する構成。

## アーキテクチャ

```
statusline        … コンテキスト使用率の常時可視化(トークンゼロ)
Stop hook         … 各レスポンス後にtranscriptを分析し状態ファイル更新(トークンゼロ)
UserPromptSubmit  … 状態を参照し、閾値超過時のみ additionalContext を注入
token-review skill… 明示呼び出し時のみロードされる詳細診断ナレッジ
/token-watch      … ON/OFF切り替えスラッシュコマンド
```

判定は Stop hook、通知は次の UserPromptSubmit という分業により、
「レスポンス後に毎回追加のAPIリクエストを発生させる」構造を回避しています。

## 検出項目

| 項目 | 方法 | 通知 |
|---|---|---|
| コンテキスト肥大 | transcriptサイズ >= 600KB(既定) | クールダウン付き警告 |
| タスク切り替え | 新プロンプト中のファイルパス/チケットID(`sc-12345`等)がセッション既出集合とゼロ重複 | クールダウン付き警告 |
| 曖昧プロンプト | 60文字以下+曖昧動詞+識別子なし | Claudeへの内部ヒントのみ(対象確認を促す) |

警告注入は「前回提案から10ターン以上」のクールダウン付き。問題がないターンは `{}` を返すだけで、
コンテキストには1トークンも追加されません。

## インストール

前提: `jq` が必要です(`brew install jq`)。

```bash
# 1. 配置
mkdir -p ~/.claude/token-watch
cp -r hooks statusline ~/.claude/token-watch/
chmod +x ~/.claude/token-watch/hooks/*.sh ~/.claude/token-watch/statusline/statusline.sh

# 2. スラッシュコマンド
mkdir -p ~/.claude/commands
cp commands/token-watch.md ~/.claude/commands/

# 3. スキル
mkdir -p ~/.claude/skills
cp -r skills/token-review ~/.claude/skills/

# 4. settings.json に settings-snippet.json の内容をマージ
#    (~/.claude/settings.json。既存のhooks設定がある場合は配列に追記)

# 5. 有効化
touch ~/.claude/token-watch/enabled
```

Claude Code を再起動(または新規セッション開始)後、`/hooks` で UserPromptSubmit / Stop に
登録されていることを確認してください。

## 使い方

- `/token-watch on` / `off` / `status` — 監視の切り替え
- `token-review スキルで診断して` — 詳細診断(costs.mdベストプラクティス準拠のレポート)
- statusline に `[Model] ▓▓▓░░░░░░░ 34% ctx | $0.55 | watch:ON` が常時表示されます

## チューニング(環境変数)

| 変数 | 既定 | 意味 |
|---|---|---|
| `TOKEN_WATCH_SIZE_WARN_KB` | 600 | transcriptサイズ警告閾値(KB) |
| `TOKEN_WATCH_COOLDOWN_TURNS` | 10 | 警告の再表示間隔(ターン) |
| `TOKEN_WATCH_MIN_TURNS` | 6 | タスク切替検出を有効にする最低ターン数 |
| `TOKEN_WATCH_VAGUE_MAX_LEN` | 60 | 曖昧プロンプト判定の最大文字数 |
| `TOKEN_WATCH_DIR` | ~/.claude/token-watch | 状態ディレクトリ |
| `TOKEN_WATCH_ID_RE` | (下記参照) | 識別子パターンの上書き(最優先) |

### 識別子パターンのカスタマイズ

タスク切替検出に使う識別子パターンは `hooks/token-watch-common.sh` で一元定義されており、
両hookが同じ定義を参照します(定義のズレによる誤検出は構造上発生しません)。

自社のチケット体系に合わせるには、パターン(ERE)を1行書いたファイルを置くだけです:

```bash
# 例: JIRAキーを自社プロジェクトに限定し、Terraform/Pythonのみ対象にする
echo '(PROJ|INFRA)-[0-9]+|[A-Za-z0-9_./-]+\.(tf|py|md)' > ~/.claude/token-watch/id-pattern
```

優先順位: `TOKEN_WATCH_ID_RE` 環境変数 > `id-pattern` ファイル > 既定値
(既定値: `sc-` 形式のShortcut ID、JIRA風 `ABC-123`、主要拡張子のファイルパス)

transcriptサイズとコンテキストトークン数の対応は内容(コード比率、ツール出力)で変わります。
まず600KBで運用し、statusline の ctx% と見比べて調整してください
(目安: 警告が出た時点の ctx% が 60〜70% になるように)。

## 既知の制限

- **タスク切替検出は「明示的に別の識別子に言及したとき」のみ**反応します。識別子を含まない
  話題転換は検出できません(設計上の割り切り。誤検出ゼロを優先)。
- ターン数カウントは transcript の user タイプ行数で近似しており、tool_result を含むため
  実ターン数より多めに出ます。クールダウンの単調カウンタとしては問題ありません。
- statusline の `context_window.used_percentage` は Claude Code のバージョンによって挙動が
  変わったことがあります。表示が `/context` と乖離する場合はバージョンを更新してください。
- 状態ファイルは30日でGCされます(`~/.claude/token-watch/sessions/`)。
