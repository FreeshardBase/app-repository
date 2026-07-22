# Overleaf — deactivated 2026-07-22

Moved out of the store during a quality cleanup. Overleaf (CE, `sharelatex/sharelatex`)
jumped `sharelatex:3` → `6.x` without its supporting config being updated, and turned
out to be a multi-fault reintegration that still does not boot cleanly. Deactivated until
someone works it end-to-end on a real shard.

## Symptom

Accessing overleaf serves shard_core's 502/splash page and never resolves. sharelatex
crash-loops on startup.

## Faults found and fixed (already applied in this compose)

Diagnosed live on shard 339 (kernel ≥6.19) via controller diagnostic `70d73ab8`
(findings in `skills/api-freeshard-diagnostics/findings-70d73ab8-*.md`). Each fault
masked the next:

1. **Support images too old.** Overleaf 6.x needs MongoDB ≥8.0 + Redis ≥7.4, mongo as a
   replica set (transactions). Compose carried `mongo:4.4`/`redis:6.2` from the 3.x era.
   → bumped to mongo 8.0.x + redis 7.4, added `--replSet overleaf` + sidecar
   `mongodb-init-replica-set.js` (mounted into `/docker-entrypoint-initdb.d`).
2. **MongoDB 8.0 vs kernel ≥6.19.** Rolling `mongo:8.0` crash-loops on kernel ≥6.19
   (SERVER-121912, TCMalloc/rseq; fatal guard `id=12257600`). → pinned **`mongo:8.0.4`**
   (predates the guard; still meets Overleaf's ≥8.0 req). Confirmed replica set
   `SET=overleaf PRIMARY` on 8.0.4. **Fragile pin** — revisit once MongoDB ships a
   TCMalloc-patched 8.0.x. Also: mongo's `rs.initiate` only runs on an EMPTY data dir, so
   a dirty `mongo_data` from a prior crash silently skips replica-set init.
3. **In-container path rename.** Overleaf 5.0+ init guard
   `000_check_for_old_bind_mounts_5.sh` refuses to start (exit 101) if you bind-mount the
   old ShareLaTeX paths. → mount target `/var/lib/sharelatex` → `/var/lib/overleaf`,
   `TEXMFVAR` updated to match.

(Also observed but not an overleaf bug: shard root disk filled to 100% during heavy-app
smoke testing, blocking container start with `no space left on device`. Free disk before
retrying.)

## Current blocker (unresolved)

After all of the above — including the `/var/lib/overleaf` rename — sharelatex **still
crash-loops with the same symptom**. The next failing init guard was not captured before
deactivation. Overleaf's boot runs a CHAIN of `/etc/my_init.d/*` guards; the next one is
unknown.

## Reactivation checklist

1. Deploy on a real shard (kernel ≥6.19, ample free disk). Do NOT trust `docker compose
   config` / image pulls alone — every fault above only appeared on a full boot.
2. Ensure `mongo_data` is empty on first boot so the replica-set init runs; confirm
   `rs.status().set == overleaf` and a `PRIMARY` member.
3. Tail `docker logs overleaf-sharelatex` and read each `my_init.d` guard that fails
   (`*** /etc/my_init.d/<script> failed with status <n>` → `Refusing to startup`); fix the
   compose to satisfy it. Repeat until sharelatex reaches a `listening`/nginx-up state.
   Likely suspects for the next guard: data-dir subpaths (`/var/lib/overleaf/data`,
   `tmp`), Server-Pro-only vars (`SANDBOXED_COMPILES_HOST_DIR*` — CE should not need
   these), or `OVERLEAF_*` vs legacy `SHARELATEX_*` env names.
4. Consider re-syncing the whole service block to Overleaf's current upstream
   `docker-compose.yml` (github.com/overleaf/overleaf) rather than patching guard-by-guard.
5. Verify end to end: `/launchpad` account creation → new project → recompile a PDF
   (exercises mongo transactions + TeXLive).
