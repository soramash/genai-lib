# genai-lib

## Sensitive info check

This repo is public. `scripts/check-sensitive-info.sh` scans for blocked
terms (see `scripts/sensitive-terms.txt`, e.g. internal names) and common
credential patterns (AWS keys, private key blocks, Slack/GitHub/Google
tokens) before they get committed.

Enable it locally as a pre-commit hook:

```sh
git config core.hooksPath .githooks
```

It also runs in CI on every push/PR (`.github/workflows/check-sensitive-info.yml`).

To run it manually:

```sh
scripts/check-sensitive-info.sh --staged   # what's about to be committed
scripts/check-sensitive-info.sh --all      # everything tracked + untracked in the repo
```

Legitimate false positives can be excluded via a `.sensitiveignore` file at
the repo root (one extended-regex path pattern per line).

### Blocklist: public vs. local terms

- `scripts/sensitive-terms.txt` is committed. Only put terms here that are
  safe to publish alongside the fact that they're blocked (e.g. this
  repo's own already-public company/handle names) — CI checks this file,
  so it's what actually gets enforced for every contributor and every push.
- `scripts/sensitive-terms.local.txt` (copy from the `.example` file) is
  gitignored, for terms too sensitive to reveal in a public blocklist
  (internal codenames, other people's names, internal hostnames, etc.).
  It's merged in automatically when present, but only on machines where
  it exists — CI never sees it, so treat it as a personal safety net, not
  a substitute for the committed list.