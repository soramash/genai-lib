# gws-suspended-archived-report

A [Claude Code](https://claude.com/claude-code) skill that lists Google
Workspace members who are currently **suspended** or **archived**, along with
the date each status was applied. Built on top of the
[`gws` CLI](https://github.com/googleworkspace/cli).

## What it does

- Queries the Admin SDK Directory API (`users.list`) with `isSuspended=true`
  and `isArchived=true`
- Extracts `suspensionTime` / `suspensionReason` for suspended members and
  `archivalTime` for archived members
- Flags members who appear on both lists
- Documents a `gws` quirk: there's no separate `directory` service name in the
  CLI — the Directory API's `users` resource is reached through the
  `admin-reports` service with `--api-version directory_v1` overridden

## Requirements

- [`gws`](https://github.com/googleworkspace/cli) installed and authenticated
  (`gws auth login`)
- An account with the `admin.directory.user.readonly` scope (or broader)
- Admin SDK enabled on the Google Cloud project backing your `gws` credentials

## Installation

Copy `SKILL.md` into your project's or user's Claude Code skills directory:

```bash
mkdir -p .claude/skills/gws-suspended-archived-report
cp SKILL.md .claude/skills/gws-suspended-archived-report/
```

Or, for a user-wide install:

```bash
mkdir -p ~/.claude/skills/gws-suspended-archived-report
cp SKILL.md ~/.claude/skills/gws-suspended-archived-report/
```

## Usage

In Claude Code, invoke it directly:

```
/gws-suspended-archived-report
```

Or just ask in natural language, e.g. "list our suspended and archived Google
Workspace members with their status dates" — Claude Code will pick up the
skill automatically once it's installed.

Under the hood it runs commands like:

```bash
gws admin-reports users list --api-version directory_v1 \
  --params '{"customer":"my_customer","query":"isSuspended=true","maxResults":500,"projection":"full"}' \
  --page-all --page-limit 20
```

See [`SKILL.md`](./SKILL.md) for the full recipe, relevant response fields,
and post-processing steps.

## Notes

- Output includes real member names and email addresses. Don't leave raw
  JSON/JSONL dumps lying around after producing the summary.
- This is a project-authored skill, not part of the official
  [googleworkspace/cli](https://github.com/googleworkspace/cli) skill set
  synced via `skills-lock.json`.

## License

MIT
