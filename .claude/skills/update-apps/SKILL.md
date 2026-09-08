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
Installed and opened on a trial shard by step 8; the result is posted as a comment on
this PR. The bundle is also here, for installing on a shard of your own:

[updated_apps.zip](https://storageaccountportab0da.blob.core.windows.net/app-store/updates/$TS/updated_apps.zip)

(Markdown link, not a fenced code block — the URL must be clickable in the rendered PR.)

## Errors / unattended apps
<list any check errors or stub NotImplementedErrors>
EOF
)"
```

### 8. Smoke-test the bundle on a trial shard

`update/smoke_test.py` does the whole post-PR check unattended: assign a trial shard,
pair, remove the apps a fresh shard ships with, then install each app from the bundle
and open it. See the "Smoke-testing a bundle" section of `agents.md` for what it does
and why each step is there.

The bundle only exists once CI's `preview` job has uploaded it, and a full run takes
about ten minutes, so wait and run in **one backgrounded command**, then end the turn
and let the completion notification bring you back. Do not poll from the foreground:
it burns turns while wall-clock barely moves.

```bash
BUNDLE="https://storageaccountportab0da.blob.core.windows.net/app-store/updates/$TS/updated_apps.zip"
( ready=""
  for i in $(seq 1 40); do
    if [ "$(curl -sS -o /dev/null -w '%{http_code}' "$BUNDLE")" = "200" ]; then ready=1; break; fi
    sleep 30
  done
  [ -n "$ready" ] || { echo "preview job did not upload the bundle within 20 minutes"; exit 1; }
  uv run update/smoke_test.py "$BUNDLE" ) > /tmp/smoke-$TS.log 2>&1
```

The loop is bounded (40 attempts, 20 minutes) so a `preview` job that never finishes
cannot spin forever. If the bundle never appears, say so and stop — do not run the
script against a URL that 404s.

When it finishes, post the summary table as a PR comment and carry it into step 10.

Two outcomes are not app failures and must not be reported as such:

- `no standby shard available` — the controller's pool is empty. Record the smoke test
  as **skipped**, and do not retry in a loop; the pool refills on its own schedule.
- An app whose `minimum_portal_size` exceeds the trial shard (currently `s`). The core
  refuses to start it and serves a splash saying so. Report it as **not testable here**,
  not as broken.

Each run consumes one standby shard, and the shard deletes itself 24h after assignment.

### 9. If an app failed: a time-boxed look, then stop

**Hard limit: 15 minutes, the list below, and no fixes.** Do not edit an app, do not
open another PR, do not reinstall in a loop. The output of this step is a paragraph in
the PR, nothing else. If 15 minutes is not enough, that is the finding: say what you
ruled out and hand it over.

The run saved its terminal session, so the shard is still reachable:

```bash
JWT=$(python3 -c "import json;print(json.load(open('update/smoke_test_session.json'))['authorization'])")
D=<shard domain from the summary table>

curl -sS --cookie "authorization=$JWT" "https://$D/core/protected/apps/<app>"
curl -sS --cookie "authorization=$JWT" "https://$D/core/protected/stats/disk"
curl -sS --cookie "authorization=$JWT" "https://$D/core/protected/management/profile"
curl -sS --cookie "authorization=$JWT" "https://$D/core/protected/stats/tasks"
curl -sS -o /dev/null -w '%{http_code}\n' --cookie "authorization=$JWT" "https://<app>.$D/"
```

What each one settles:

- **`apps/<app>`** — `status` and `status_message`. An `error` here usually carries the
  real cause (a failed image pull, an invalid compose) and often ends the investigation.
- **`stats/disk`** — `disk_space_low` is true when the volume is nearly full, and that
  stops *every* app and starts none. It presents as an app bug and is not one.
- **`management/profile`** — `vm_size` against the app's `minimum_portal_size`.
- **`stats/tasks`** — whether the installation worker is still busy or wedged.
- **the app URL** — the current response, read with the same eyes as the script: a 502/503
  splash means still starting, a 404 means no Traefik router (queued, ERROR, or the
  dynamic config was mid-rewrite), and a 200 carrying the web terminal's page means the
  app has no route at all.

There is **no container-log endpoint** on the shard core. Do not go looking for one;
`status_message` plus the above is what is available unattended. Deeper digging needs an
operator-opened diagnostic, which is the user's call, not this skill's.

### 10. Print final summary

Per-app table: `[AUTO]` / `[REVIEW]` / `[ERROR]`, current → new, reason. Note any icon refreshes. Include the PR URL and the smoke-test bundle URL, the smoke-test result per app (install and start durations, or why it was skipped), and anything step 9 turned up.

## Notes

- The `update.py apply` step runs `docker compose pull --dry-run` and aborts on failure; failed apps appear in `git status` as uncommitted edits if the abort path leaves them so — the skill's apply loop should `git checkout -- apps/<app>` to clean.
- The skill never auto-merges. The PR stays open for the user to inspect and merge; step 8 replaces the manual smoke install, it does not replace the user's judgement about merging.
- The smoke test is deliberately not a CI job: a run takes tens of minutes and consumes a standby shard.
- Storage path `app-store/updates/$TS/updated_apps.zip` is deterministic; PR number is NOT in the URL — it is unknown when the PR description is written.
- Recurring `apply` pull failures are registry lag, not bad versions — record as errors and continue, don't retry:
  - ACR-mirrored apps (`filebrowser`, `mirotalk`, `mosquitto` → `portalapps.azurecr.io/ptl-apps/*`): new upstream tag must be pushed into ACR before the runner can pull it.
  - Variant-tag apps (e.g. `glances` `nicolargo/glances:X-full`): the `-full`/`-nginx` variant can lag the plain tag on the registry — `4.5.5-full` failed dry-run while `4.5.4-full` was current. Same transient failure, not a flavor-tag skip.
- Flavor-tag non-upgrades (same version, different variant suffix, e.g. `baikal 0.10.1 → 0.10.1-nginx`) are not real updates — skip, don't apply.
- Support-image drift is real and has bitten us: **overleaf** 6.x needed mongo 4.4→8.0 (as a replica set) + redis 6.2→7.4 and wouldn't start until fixed; **affine** pinned plain `postgres:16` but needs `pgvector/pgvector:pg16` (predeploy runs `CREATE EXTENSION vector`); **immich** pins its own postgres/vchord image and bumps it independently of the server version. On any major app bump, run the support-image check in step 4. Sidecar files (e.g. a mongo replica-set init script) ship verbatim next to the compose (`{{ fs.installation_dir }}/<file>`) — see `add-app` digest.
