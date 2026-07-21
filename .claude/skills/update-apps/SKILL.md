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

**Support-image check (major bumps especially).** `update.py` only tracks the app's own image tag — it is blind to the versions of **support images** (mongo, postgres, redis, mariadb, meilisearch, …) pinned in `docker-compose.yml.template`. A major app bump can silently raise the required DB/cache version and the app then won't start. For any **major** jump (and when diagnosing a stuck app): fetch the upstream project's reference `docker-compose.yml`/self-host compose and diff its support-image tags **and init requirements** (e.g. mongo replica set, `pgvector` extension) against ours. If ours is below the requirement → **review**, and fix the support image in the same PR.

> Bumping a support image across an **on-disk-incompatible major** (postgres N→N+1, mongo skipping a major, meilisearch dump-version change) breaks existing shards' data volumes — those need a manual per-shard migration and are **not** a drop-in compose edit. A same-major swap (e.g. `postgres:16` → `pgvector/pgvector:pg16`) is drop-in. Call out which case in the PR.

Record a one-line reason per app. The reason becomes the commit message body line.

### 5. Apply each app

For each app, in any order:

```bash
python3 update/update.py apply <app> <latest> --auto --branch-ts "$TS"
# or
python3 update/update.py apply <app> <latest> --review --branch-ts "$TS" --reason "<one line>"
```

If `apply` exits non-zero (docker pull failure), record and continue with remaining apps.

### 6. Refresh changed app icons

Only for apps in **this run's update set** (auto or review) — don't audit every app. A version bump often ships a rebrand; the store icon is stale otherwise.

For each updated app:

1. Read the icon filename from `apps/<app>/app_meta.json` (`"icon": "<file>"`) and the `upstream_repo`.
2. Locate the upstream brand asset. Enumerate the repo tree and grep for logo/icon assets:
   ```bash
   gh api "repos/<owner>/<repo>/git/trees/HEAD?recursive=1" --jq '.tree[].path' \
     | grep -iE 'logo|favicon|icon' | grep -iE '\.(svg|png)$' \
     | grep -ivE 'app/views/icons/_|node_modules|test|spec'
   ```
   Common good hits: `public/favicon.svg`, `public/logo.svg`, `assets/logo.svg`. Prefer a **self-contained tile form** (mark on a solid/white background, e.g. `favicon.svg`) over a bare transparent mark.
3. Fetch it and compare to the current `apps/<app>/<icon>`. A changed dominant fill/color, a different `viewBox`, or a visibly different mark = rebrand. (A pure byte diff from reformatting is not — eyeball the colors/paths.)
4. **If changed:** overwrite `apps/<app>/<icon>` with the new asset, keeping the **same filename** referenced in `app_meta.json` (regardless of the upstream filename). Commit separately:
   ```bash
   git commit -m "chore(<app>): refresh icon to new upstream brand logo"
   ```
   Record it for the PR "Icon changes" section (old → new dominant color / short note).
5. **If unchanged or no clear upstream asset:** leave it.

### 7. Push branch and open PR

```bash
git push -u origin "updates/$TS"
gh pr create --base main --head "updates/$TS" --title "App updates $TS" --body "$(cat <<EOF
## Summary
<table of auto vs review apps, one line each>

## Icon changes
<list apps whose icon was refreshed in step 6, old → new; omit section if none>

## Smoke-test bundle
After CI completes the `preview` job, download and bulk-install on a fresh shard:

[updated_apps.zip](https://storageaccountportab0da.blob.core.windows.net/app-store/updates/$TS/updated_apps.zip)

(Markdown link, not a fenced code block — the URL must be clickable in the rendered PR.)

## Errors / unattended apps
<list any check errors or stub NotImplementedErrors>
EOF
)"
```

### 8. Print final summary

Per-app table: `[AUTO]` / `[REVIEW]` / `[ERROR]`, current → new, reason. Note any icon refreshes. Include the PR URL and the smoke-test bundle URL.

## Notes

- The `update.py apply` step runs `docker compose pull --dry-run` and aborts on failure; failed apps appear in `git status` as uncommitted edits if the abort path leaves them so — the skill's apply loop should `git checkout -- apps/<app>` to clean.
- The skill never auto-merges. The PR stays open for the user to inspect, run smoke install, and merge.
- Storage path `app-store/updates/$TS/updated_apps.zip` is deterministic; PR number is NOT in the URL — it is unknown when the PR description is written.
- Recurring `apply` pull failures are registry lag, not bad versions — record as errors and continue, don't retry:
  - ACR-mirrored apps (`filebrowser`, `mirotalk`, `mosquitto` → `portalapps.azurecr.io/ptl-apps/*`): new upstream tag must be pushed into ACR before the runner can pull it.
  - Variant-tag apps (e.g. `glances` `nicolargo/glances:X-full`): the `-full`/`-nginx` variant can lag the plain tag on the registry — `4.5.5-full` failed dry-run while `4.5.4-full` was current. Same transient failure, not a flavor-tag skip.
- Flavor-tag non-upgrades (same version, different variant suffix, e.g. `baikal 0.10.1 → 0.10.1-nginx`) are not real updates — skip, don't apply.
- Support-image drift is real and has bitten us: **overleaf** 6.x needed mongo 4.4→8.0 (as a replica set) + redis 6.2→7.4 and wouldn't start until fixed; **affine** pinned plain `postgres:16` but needs `pgvector/pgvector:pg16` (predeploy runs `CREATE EXTENSION vector`); **immich** pins its own postgres/vchord image and bumps it independently of the server version. On any major app bump, run the support-image check in step 4. Sidecar files (e.g. a mongo replica-set init script) ship verbatim next to the compose (`{{ fs.installation_dir }}/<file>`) — see `add-app` digest.
