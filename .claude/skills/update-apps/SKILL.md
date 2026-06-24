---
name: update-apps
description: Use to run the bi-weekly Freeshard app update pass. Orchestrates the deterministic `update/update.py` CLI, judges breaking-change candidates with LLM reasoning, opens a PR with the smoke-test bundle URL embedded.
---

# /update-apps — Freeshard App Update Pass

## When to use

User invokes `/update-apps` or asks to "run app updates", "check for updates", "bump app versions". Repo must be `freeshard/app-repository`.

## Flow

### 1. Compute the run timestamp

```bash
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
echo "$TS"
```

This `$TS` is reused as `updates/$TS` branch name and `app-store/updates/$TS/updated_apps.zip` storage path. Save it for the PR description.

### 2. Run check

```bash
python3 update/update.py check --json > update/update_info/latest_check.json
```

(The check subcommand also writes that file; the redirect is belt-and-suspenders for the skill.)

### 3. Partition apps

Read `update/update_info/latest_check.json`. For each app entry:

- `status == "up_to_date"` → ignore.
- `status == "no_script"` → log warning; skip.
- `status == "error"` → log error; skip; surface in the final summary.
- `status == "outdated"`:
  - **Clean auto** iff: `semver_jump` ∈ {`patch`, `minor`} AND NOT `release_body_has_breaking` AND NOT `compose_diff_nontrivial`. Action: `apply --auto`.
  - Otherwise → **candidate**. Read `release_body_snippet`, `upstream_compose_diff`, `candidate_reasons`. Judge.

### 4. Judge each candidate

For each candidate app, decide auto vs review by reading the spec'd signals:

- Major-jump with a release-notes section titled "Migration" or describing schema/config changes the operator must perform → **review**.
- "Breaking" mentioned but only refers to a removed deprecated flag/env-var Freeshard doesn't set (cross-check against `docker-compose.yml.template`) → **auto**.
- Compose diff adds/removes a service, changes a volume, renames an env var → **review**.
- Compose diff adds an optional env with sensible default → **auto** with one-line reason.
- Default on ambiguity: **review**.

Record a one-line reason per app. The reason becomes the commit message body line.

### 5. Apply each app

For each app, in any order:

```bash
python3 update/update.py apply <app> <latest> --auto --branch-ts "$TS"
# or
python3 update/update.py apply <app> <latest> --review --branch-ts "$TS" --reason "<one line>"
```

If `apply` exits non-zero (docker pull failure), record and continue with remaining apps.

### 6. Push branch and open PR

```bash
git push -u origin "updates/$TS"
gh pr create --base main --head "updates/$TS" --title "App updates $TS" --body "$(cat <<EOF
## Summary
<table of auto vs review apps, one line each>

## Smoke-test bundle
After CI completes the `preview` job, download and bulk-install on a fresh shard:

[updated_apps.zip](https://storageaccountportab0da.blob.core.windows.net/app-store/updates/$TS/updated_apps.zip)

(Markdown link, not a fenced code block — the URL must be clickable in the rendered PR.)

## Errors / unattended apps
<list any check errors or stub NotImplementedErrors>
EOF
)"
```

### 7. Print final summary

Per-app table: `[AUTO]` / `[REVIEW]` / `[ERROR]`, current → new, reason. Include the PR URL and the smoke-test bundle URL.

## Notes

- The `update.py apply` step runs `docker compose pull --dry-run` and aborts on failure; failed apps appear in `git status` as uncommitted edits if the abort path leaves them so — the skill's apply loop should `git checkout -- apps/<app>` to clean.
- The skill never auto-merges. The PR stays open for the user to inspect, run smoke install, and merge.
- Storage path `app-store/updates/$TS/updated_apps.zip` is deterministic; PR number is NOT in the URL — it is unknown when the PR description is written.
- Recurring `apply` pull failures are registry lag, not bad versions — record as errors and continue, don't retry:
  - ACR-mirrored apps (`filebrowser`, `mirotalk`, `mosquitto` → `portalapps.azurecr.io/ptl-apps/*`): new upstream tag must be pushed into ACR before the runner can pull it.
  - Variant-tag apps (e.g. `glances` `nicolargo/glances:X-full`): the `-full`/`-nginx` variant can lag the plain tag on the registry — `4.5.5-full` failed dry-run while `4.5.4-full` was current. Same transient failure, not a flavor-tag skip.
- Flavor-tag non-upgrades (same version, different variant suffix, e.g. `baikal 0.10.1 → 0.10.1-nginx`) are not real updates — skip, don't apply.
