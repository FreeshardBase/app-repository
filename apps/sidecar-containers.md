# Sidecar containers

A **sidecar** is a tiny, idempotent container templated into a specific
app's own `docker-compose.yml.template` that reconciles state against that
app's own API to do setup/migration work the app itself doesn't do on its
own. Lifetime is a per-sidecar choice, not a pipeline-wide rule:

- **One-shot** — runs a single reconcile pass, then exits cleanly
  (`restart: "no"`).
- **Long-lived** — keeps running, reconciling on an internal loop or poll
  (`restart: always`). Useful when whatever the sidecar reacts to can happen
  while the app is already running and nothing restarts the app's stack to
  catch it — e.g. creating an app account when a family member is added to
  the shard.

Only the compose wiring and the container's own entrypoint differ between
the two; everything else below — idempotency, the exit/log contract,
versioning and publishing — applies to both. Each sidecar is app-specific —
there is no shared base image or shared sidecar repo, because the APIs
sidecars talk to (e.g. Paperless's Django/allauth API vs. Immich's admin
API) share nothing worth abstracting over.

This doc is the contract every sidecar is expected to follow. It exists
because the pipeline that builds and publishes sidecar images
(`.github/workflows/sidecars.yml`) ships before any real sidecar does — see
`sidecar-template/sidecar/` for a minimal worked example of the one-shot
shape that exercises the same contract without talking to any real app.

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
run unattended on customer shards, and a failed sidecar needs
`docker exec`-level debuggability (a shell, `python3` on PATH) more than the
~15MB a distroless base would save.

That tradeoff was reasoned about for the one-shot shape, where the container
is only resident for the length of one reconcile pass — image size on disk
is what matters there. A long-lived sidecar stays resident for the shard's
uptime instead, so its dominant sizing criterion is runtime memory
footprint, not image size. Don't assume the one-shot reasoning above carries
over unchanged: benchmark the actual resident footprint of the stdlib-only
Python baseline before committing to it for a long-lived sidecar.

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

- **Lifetime, via `restart`** — `"no"` for a one-shot sidecar: it must not
  restart-loop after a clean exit. The render context re-runs
  `docker compose up` on every app startup, so the sidecar container itself
  runs again on every start; `restart: "no"` just stops Docker from
  respawning it *within* a single run after it has already exited 0.
  `always` for a long-lived sidecar: the container keeps running and
  reconciling on its own internal loop/poll, and a crash gets the same
  automatic restart any other long-lived compose service gets.
- `depends_on: { <app-service>: { condition: service_healthy } }` — the
  sidecar must not start running against the app before the app is actually
  ready to answer, for either shape. This means **any app adopting a
  sidecar needs a healthcheck defined on its own service first** — that's a
  prerequisite of adopting a sidecar, not something the sidecar pipeline
  adds for you. Note this only gates the container's initial start: nothing
  re-checks `service_healthy` once the stack is up, so a long-lived
  sidecar's own loop still needs to tolerate the app being briefly
  unreachable afterwards (a restart, maintenance, etc.) — see the exit/log
  contract below for how that failure gets handled.

Example (one-shot):

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

For a long-lived sidecar, the wiring is identical except for the `restart`
line (the container's own entrypoint also differs — a loop instead of a
single pass, see the exit/log contract below):

```yaml
  my-app-sidecar:
    image: ghcr.io/freeshardbase/my-app-sidecar:0.1.0
    container_name: my-app-sidecar
    restart: always
    depends_on:
      my-app:
        condition: service_healthy
    environment:
      - BASE_URL=http://my-app:8080
    networks:
      - my-app
```

## Idempotency contract

A sidecar does not blindly apply its change on every reconcile pass — it:

1. **GET**s the current state from the target app's own API.
2. **Compare**s it against the desired state.
3. **PATCH**es only on mismatch.

If the state is already correct, that is a clean, successful pass — not an
error. This is what makes it safe to repeat the check: a one-shot sidecar
exits 0 and the next pass is simply the next container run (the app's next
startup); a long-lived sidecar loops back and reconciles again on its own
schedule.

## Exit and log contract

Every reconcile pass — the entire lifetime of a one-shot run, or one
iteration of a long-lived sidecar's loop — has exactly three possible
outcomes:

| Outcome | Log line |
|---|---|
| Nothing to do yet (already correct, or precondition not met) | `INFO` describing what was checked |
| Applied a change | `INFO` naming what changed |
| Real failure (couldn't reach the app, patch rejected, etc.) | `ERROR` describing the failure |

How a pass's outcome maps onto the process depends on the shape:

- **One-shot** — the pass is the whole process: nothing-to-do and
  applied-a-change both exit `0`; a real failure exits non-zero.
- **Long-lived** — nothing-to-do and applied-a-change are logged and the
  loop continues; the process never exits on either of those outcomes. A
  real failure is logged as `ERROR`, and whether the sidecar retries on the
  next pass or exits (letting `restart: always` restart the container with
  a clean slate) is the sidecar's own call — retry for a failure that looks
  transient (e.g. the app briefly unreachable), exit for one that doesn't.

A sidecar should log to stdout/stderr (no file logging) so `docker logs`
and `docker compose logs` show the outcome directly, for either shape.

## Reference implementation

`sidecar-template/sidecar/` is a minimal, no-op sidecar that follows this
contract exactly (`get_current_state`/`apply_patch`, GET-compare-PATCH,
three-outcome exit/log). It exemplifies the **one-shot** shape specifically:
`main()` runs a single reconcile pass and returns. A long-lived sidecar
follows the same GET-compare-PATCH and three-outcome contract but wraps that
pass in its own loop/poll instead of returning after one; there is no
long-lived reference implementation yet (real future work, not this doc).
It exists only to validate the build/publish pipeline end-to-end before any
real sidecar exists; copy its shape rather than its content when writing a
real one — and if that real one is long-lived, copy the reconcile logic's
shape, not its one-shot lifetime. It is **not** inside `apps/` —
`build_store_data.py` and `update/update.py` both iterate every directory
under `apps/` expecting a real `app_meta.json`, and the template is not an
installable app.

## Planned consumers

The first real sidecars (tracked separately, not part of the pipeline work
itself) are expected to patch Paperless-ngx's and Immich's admin-account
email to the shard owner's verified email, so each app's native OIDC
auto-link can fire on first login.
