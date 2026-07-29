---
name: gws-suspended-archived-report
description: "List Google Workspace suspended and archived members with their suspension/archival dates, via gws admin-reports (Directory API)."
metadata:
  version: "1.0.0"
  custom: true
  openclaw:
    category: "productivity"
    requires:
      bins:
        - gws
    cliHelp: "gws admin-reports users list --api-version directory_v1 --help"
---

# gws-suspended-archived-report

Custom project skill (not synced from googleworkspace/cli). Produces two dated
lists: members currently **suspended** and members currently **archived**, using
the `gws` CLI against the Admin SDK Directory API.

> **PREREQUISITE:** Run `gws auth status` first to confirm OAuth is set up and
> `admin.googleapis.com` is enabled. The authenticated account needs the
> `https://www.googleapis.com/auth/admin.directory.user.readonly` scope (or
> broader). If auth fails, run `gws auth login`.

## Key trick: no separate "directory" service

`gws`'s built-in `admin-reports` service defaults to the Admin SDK **Reports**
API (`reports_v1`) and its resources (`activities`, `userUsageReport`, ...).
There is no separate `directory` or `admin-directory` service name — `gws
directory ...` and `gws admin ...` both fail with "Unknown service".

The Directory API's `users` resource lives in the **same** Admin SDK, so it is
reached by keeping the `admin-reports` service name but overriding the API
version:

```bash
gws admin-reports users list --api-version directory_v1 --params '{...}'
```

`gws schema` does not resolve `users` under `admin-reports` (it only lists the
reports_v1 resources), so don't rely on it here — the flags below are known-good.

## Commands

Always dry-run first to sanity check the request shape:

```bash
gws admin-reports users list --api-version directory_v1 \
  --params '{"customer":"my_customer","query":"isSuspended=true","maxResults":500,"projection":"full"}' \
  --dry-run
```

Then fetch for real, paginating fully (`--page-all` emits one JSON line per page):

```bash
# Suspended members
gws admin-reports users list --api-version directory_v1 \
  --params '{"customer":"my_customer","query":"isSuspended=true","maxResults":500,"projection":"full"}' \
  --page-all --page-limit 20 > suspended_raw.jsonl

# Archived members
gws admin-reports users list --api-version directory_v1 \
  --params '{"customer":"my_customer","query":"isArchived=true","maxResults":500,"projection":"full"}' \
  --page-all --page-limit 20 > archived_raw.jsonl
```

`customer: "my_customer"` is a Directory API alias meaning "the caller's own
Google Workspace customer" — no need to look up the real customer ID.

## Relevant fields

- Suspended users: `suspensionTime` (ISO 8601 UTC) and `suspensionReason`
  (commonly `"ADMIN"` for manual admin suspension).
- Archived users: `archivalTime` (ISO 8601 UTC).
- Both objects also carry `suspended` and `archived` booleans — check them on
  the *other* list to flag members who are both suspended and archived.
- `primaryEmail`, `name.fullName`, `orgUnitPath` are useful for display.

## Post-processing

Parse each JSONL file (one JSON object per page; merge `users` arrays across
pages if `--page-limit` was hit), then sort by the date field descending and
render a table: date, email, name, and a flag for cross-membership between the
two lists.

```bash
python3 -c "
import json
with open('suspended_raw.jsonl') as f:
    pages = [json.loads(l) for l in f]
users = [u for p in pages for u in p.get('users', [])]
users.sort(key=lambda u: u.get('suspensionTime') or '', reverse=True)
for u in users:
    print(u.get('suspensionTime'), u.get('primaryEmail'), u.get('name', {}).get('fullName'))
"
```

Check `nextPageToken` is absent on the last page (or that `--page-limit` wasn't
hit) to confirm the list is complete rather than truncated.

## Data handling

These lists contain real employee names and email addresses. Once the summary
table has been produced for the user, delete any raw JSON/JSONL dumps left in
the scratchpad — don't let full user-directory exports linger on disk longer
than needed for the task.
