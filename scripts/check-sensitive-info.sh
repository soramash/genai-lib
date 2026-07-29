#!/usr/bin/env bash
#
# check-sensitive-info.sh
#
# Scans files for names/terms that must not appear in this public repo
# (see scripts/sensitive-terms.txt, plus an optional gitignored
# scripts/sensitive-terms.local.txt for terms too sensitive to publish in
# the term list itself — see note below) and for common credential
# patterns (AWS access keys, private key blocks, Slack/GitHub/Google API
# tokens).
#
# NOTE on sensitive-terms.local.txt: it is gitignored, so it only exists on
# machines where someone created it, and CI checks out a clean tree without
# it. That means terms placed only in the local file are enforced on your
# machine but NOT in CI. Keep anything you need enforced repo-wide (for
# everyone, via CI) in the committed sensitive-terms.txt instead.
#
# Usage:
#   scripts/check-sensitive-info.sh              # scan staged (index) content — used by pre-commit
#   scripts/check-sensitive-info.sh --staged     # same as above, explicit
#   scripts/check-sensitive-info.sh --all        # scan every tracked + untracked (non-ignored) file on disk
#
# Exceptions: add path patterns (extended-regex, matched against the
# repo-relative path) to .sensitiveignore at the repo root, one per line.
#
# Exit status: 0 = clean, 1 = sensitive content found, 2 = usage/setup error.
#
# Written for bash 3.2 (macOS default) compatibility: no mapfile/readarray,
# no unguarded expansion of possibly-empty arrays under `set -u`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
TERMS_FILE="$SCRIPT_DIR/sensitive-terms.txt"
LOCAL_TERMS_FILE="$SCRIPT_DIR/sensitive-terms.local.txt"
IGNORE_FILE="$REPO_ROOT/.sensitiveignore"

MODE="${1:---staged}"
case "$MODE" in
  --staged|--all) ;;
  *)
    echo "Usage: $0 [--staged|--all]" >&2
    exit 2
    ;;
esac

if [ ! -f "$TERMS_FILE" ]; then
  echo "check-sensitive-info: terms file not found: $TERMS_FILE" >&2
  exit 2
fi

TERM_PATTERN="$(grep -h -v -E '^[[:space:]]*(#|$)' "$TERMS_FILE" | paste -sd '|' -)"

if [ -f "$LOCAL_TERMS_FILE" ]; then
  LOCAL_TERM_PATTERN="$(grep -h -v -E '^[[:space:]]*(#|$)' "$LOCAL_TERMS_FILE" | paste -sd '|' -)"
  if [ -n "$LOCAL_TERM_PATTERN" ]; then
    TERM_PATTERN="$TERM_PATTERN|$LOCAL_TERM_PATTERN"
  fi
fi

SECRET_PATTERN='(AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}'
SECRET_PATTERN="$SECRET_PATTERN"'|-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----'
SECRET_PATTERN="$SECRET_PATTERN"'|xox[baprs]-[0-9A-Za-z-]+'
SECRET_PATTERN="$SECRET_PATTERN"'|gh[pousr]_[0-9A-Za-z]{36,}'
SECRET_PATTERN="$SECRET_PATTERN"'|AIza[0-9A-Za-z_-]{35}'

# --- build the file list for the selected mode -----------------------------

if [ "$MODE" = "--staged" ]; then
  FILES_RAW="$(git -C "$REPO_ROOT" diff --cached --name-only --diff-filter=ACMR)"
else
  FILES_RAW="$(git -C "$REPO_ROOT" ls-files --cached --others --exclude-standard)"
fi

EXCLUDE_REGEX='^scripts/sensitive-terms\.txt$|^scripts/sensitive-terms\.local\.txt$|^scripts/check-sensitive-info\.sh$'
if [ -f "$IGNORE_FILE" ]; then
  while IFS= read -r line; do
    case "$line" in
      ''|'#'*) continue ;;
    esac
    EXCLUDE_REGEX="$EXCLUDE_REGEX|$line"
  done < "$IGNORE_FILE"
fi

FILES=()
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if printf '%s\n' "$f" | grep -q -E "$EXCLUDE_REGEX"; then
    continue
  fi
  FILES+=("$f")
done < <(printf '%s\n' "$FILES_RAW")

if [ "${#FILES[@]}" -eq 0 ]; then
  exit 0
fi

# --- scan --------------------------------------------------------------

found=0

run_grep() {
  local pattern="$1"
  local label="$2"
  local output

  if [ "$MODE" = "--staged" ]; then
    # Read staged blob content from the index, not the working tree, so a
    # partially-staged file (`git add -p`) is checked as it will actually
    # be committed.
    output="$(git -C "$REPO_ROOT" grep --cached -n -i -w -E "$pattern" -- "${FILES[@]}" 2>/dev/null || true)"
  else
    output="$(cd "$REPO_ROOT" && grep -n -i -w -E -I "$pattern" -- "${FILES[@]}" 2>/dev/null || true)"
  fi

  if [ -n "$output" ]; then
    echo "== $label =="
    echo "$output"
    echo
    found=1
  fi
}

run_grep "$TERM_PATTERN" "Blocked term found (see scripts/sensitive-terms.txt)"
run_grep "$SECRET_PATTERN" "Possible credential/secret found"

if [ "$found" -eq 1 ]; then
  echo "check-sensitive-info: commit blocked." >&2
  echo "Remove or redact the content above, or add a legitimate exception to .sensitiveignore." >&2
  exit 1
fi

exit 0
