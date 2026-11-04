# Deployment gotchas

Recurring failure modes when integrating an app. Consult during phase 3 (proposal) and phase 4 (scaffold).

## Non-root image + bind mounts → EACCES crash loop

Freeshard `fs.app_data` bind mounts are created **root-owned** by the Docker daemon. If the app's image runs as a **non-root user** (e.g. `node` uid 1000, common for Node apps), it cannot write to its mounted dirs → `EACCES: permission denied` on first write → crash loop.

**Symptom:** log line like `error: ... EACCES: permission denied, open '/app/.../something.log'`, container restarting.

**Fix:** add `user: "0:0"` to the service (run as root). Precedent: `vikunja`, `librechat`.

**Detect early:** check the image's `USER` — `docker image inspect <img> --format '{{.Config.User}}'` (must be pulled first), or read the upstream Dockerfile for a `USER` directive. Non-empty / non-root → likely needs `user: "0:0"` when it writes to bind mounts.

## Repos that flag every GitHub release as `prerelease`

Some projects mark **all** releases `prerelease` (never promote a stable one). `update/update_lib.py`'s `latest_github_release` skips prereleases → raises `no matching release` → the app never sees updates, and `/releases/latest` 404s.

**Fix:** in `update_check.py`, track the registry tags instead — `latest_ghcr_tag("<org>/<image>", filter_regex=r"^v\d+\.\d+\.\d+$")` (drops rc/dev/latest), and fetch notes per-tag with `github_release_body("<org>/<repo>", version)` (works for prerelease tags). Precedent: `librechat`.

**Detect:** `gh api repos/<org>/<repo>/releases --jq '[.[].prerelease] | all'` → `true` means every release is prerelease.

## Env var that sounds like "disable auth" often isn't

Some self-hosted apps ship a flag like `DISABLE_LOGIN` that reads as "skip auth entirely" but actually means "assume some other mechanism already authenticates, so block the native login page instead." Freeshard's pairing proxy doesn't mint an app-level session, so setting it leaves the app permanently unreachable (403 on load).

**Fix:** read the app's own auth middleware source before using such a flag, not just the doc's one-line description. Precedent: `umami`'s `DISABLE_LOGIN` (`docker/proxy.ts`), caught via a live 403 on install.

## `idle_time_for_shutdown` drops unsolicited inbound traffic silently

An app with a public ingestion endpoint (webhook, analytics beacon, IoT message) has no retry if the container is asleep at cold-start time — the request is just dropped. This applies even when the app's other traffic (an owner dashboard) looks like ordinary idle-shutdown-friendly browsing.

**Fix:** set `lifecycle: { "always_on": true }` whenever any path is `public` and receives traffic at unpredictable times, not just the already-named IoT/messaging bucket. Precedent: `umami`'s `/api/send` beacon endpoint.

