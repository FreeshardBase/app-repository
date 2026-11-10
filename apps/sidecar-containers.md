# Sidecar containers

A **sidecar** is a tiny, one-shot, idempotent container templated into a
specific app's own `docker-compose.yml.template` that runs once against that
app's own API to do setup/migration work, then exits cleanly. Each sidecar is
app-specific — there is no shared base image or shared sidecar repo, because
the APIs sidecars talk to (e.g. Paperless's Django/allauth API vs. Immich's
admin API) share nothing worth abstracting over.

This doc is the contract every sidecar is expected to follow. It exists
because the pipeline that builds and publishes sidecar images
(`.github/workflows/sidecars.yml`) ships before any real sidecar does — see
`sidecar-template/sidecar/` for a minimal worked example that exercises the
same contract without talking to any real app.

## Code location

```
apps/<app>/sidecar/
  Dockerfile
  VERSION
  <script(s)>
```

Lives next to that app's own `app_meta.json` and `docker-compose.yml.template`
inside `apps/<app>/`, not in a separate repo.

## Language and image

Python, stdlib only (`urllib`, `json` — no `requests` or other pip
dependencies), on `python:3.13-alpine`. Deliberately not distroless: these
run unattended on customer shards, and a failed one-shot script needs
`docker exec`-level debuggability (a shell, `python3` on PATH) more than the
~15MB a distroless base would save.

## Versioning and publishing

Each sidecar's own `VERSION` file holds its current version (e.g. `0.1.0`).
`.github/workflows/sidecars.yml` builds and pushes
`ghcr.io/freeshardbase/<app>-sidecar:<version>` whenever a push to `main`
changes files under that sidecar's directory, tagged with whatever
`VERSION` says. There is no CI auto-`latest` tag — a new published version
is always a deliberate bump to `VERSION`, committed to `main` like any other
change. The workflow will refuse to publish a version tag that already
exists in the registry, so publishing a change requires bumping `VERSION`
first.

## Compose wiring contract

An app that adopts a sidecar wires it into its own
`docker-compose.yml.template` as a normal service, with two required
settings:

- `restart: "no"` — the sidecar must not restart-loop after a clean exit.
  The render context re-runs `docker compose up` on every app startup, so
  the sidecar container itself runs again on every start; `restart: "no"`
  just stops Docker from respawning it *within* a single run after it has
  already exited 0.
- `depends_on: { <app-service>: { condition: service_healthy } }` — the
  sidecar must not start running against the app before the app is actually
  ready to answer. This means **any app adopting a sidecar needs a
  healthcheck defined on its own service first** — that's a prerequisite of
  adopting a sidecar, not something the sidecar pipeline adds for you.

Example:

```yaml
services:
  my-app:
    # ... existing service ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 10

  my-app-sidecar:
    image: ghcr.io/freeshardbase/my-app-sidecar:0.1.0
    container_name: my-app-sidecar
    restart: "no"
    depends_on:
      my-app:
        condition: service_healthy
    environment:
      - BASE_URL=http://my-app:8080
    networks:
      - my-app
```

## Idempotency contract

A sidecar does not blindly apply its change on every run — it:

1. **GET**s the current state from the target app's own API.
2. **Compare**s it against the desired state.
3. **PATCH**es only on mismatch.

If the state is already correct, that is a clean, successful run — exit 0,
not an error. This is what makes it safe for the sidecar to run again on
every single app startup.

## Exit and log contract

There are exactly three outcomes:

| Outcome | Exit code | Log line |
|---|---|---|
| Nothing to do yet (already correct, or precondition not met) | `0` | `INFO` describing what was checked |
| Applied a change | `0` | `INFO` naming what changed |
| Real failure (couldn't reach the app, patch rejected, etc.) | non-zero | `ERROR` describing the failure |

A sidecar should log to stdout/stderr (no file logging) so `docker logs`
and `docker compose logs` show the outcome directly.

## Reference implementation

`sidecar-template/sidecar/` is a minimal, no-op sidecar that follows this
contract exactly (`get_current_state`/`apply_patch`, GET-compare-PATCH,
three-outcome exit/log). It exists only to validate the build/publish
pipeline end-to-end before any real sidecar exists; copy its shape rather
than its content when writing a real one. It is **not** inside `apps/` —
`build_store_data.py` and `update/update.py` both iterate every directory
under `apps/` expecting a real `app_meta.json`, and the template is not an
installable app.

## Planned consumers

The first real sidecars (tracked separately, not part of the pipeline work
itself) are expected to patch Paperless-ngx's and Immich's admin-account
email to the shard owner's verified email, so each app's native OIDC
auto-link can fire on first login.
