# Freeshard App-Integration Reference Digest

> Sources: agents.md (primary) + docs.freeshard.net developer docs (crawled 2026-09-28)
> + the published `app_meta` JSON schema (re-fetched, still v1.2 at path `0-30-2`).
> Where they disagree this digest notes which source wins and why.

---

## App Model

An app is a Docker Compose project installed onto a user's shard (single-tenant VM). The shard:
- Renders the `docker-compose.yml.template` at install time (variable substitution)
- Uses `app_meta.json` to configure its reverse proxy, lifecycle manager, and app store display
- Routes HTTP traffic via subdomain: `<app-name>.<shard-id>.<domain>` → app container port
- Routes MQTT traffic on port 8883 (no access control; raw TLS termination only)
- Terminates TLS itself — certificates are valid for all subdomains; developers never handle certs
- Provides a splash screen while containers start on first request

**Fundamental constraints from dev docs:**
- One container must serve HTTP (not HTTPS) on a configured port
- UI must be responsive (notebook / tablet / smartphone)
- No external SaaS dependencies; only internal shard services
- No manual post-install configuration required; apps must self-configure on first start
- Each shard is owned and used by **one** person — do not require account creation or a login
  screen. Access control is the shard's job, not the app's.

---

## `app_meta.json` Schema

Schema URL (re-verified 2026-09-28, resolves, unchanged):
`https://storageaccountportab0da.blob.core.windows.net/json-schema/0-30-2/schema_app_meta_1.2.json`

The docs still point at this exact URL — **no newer schema version is published**. Latest format
version remains `1.2`. (Older apps in this repo still carry `"v": "1.0"`, e.g. immich; that is
legacy, not a target.)

### Root fields

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| `v` | string | Y | — | Format version. Use `"1.2"` for new apps |
| `app_version` | string | Y | — | Must match Docker image tag |
| `name` | string | Y | — | Lowercase, `[a-z0-9-]` only; must match folder name; becomes subdomain |
| `pretty_name` | string | Y | — | Display name (v1.1+) |
| `icon` | string | Y | — | Filename in app folder; PNG / JPEG / SVG |
| `homepage` | string | N | — | App homepage URL (v1.2+) |
| `upstream_repo` | string | N | — | GitHub repo URL for auto-update checking (v1.2+) |
| `entrypoints` | array | Y | — | See below |
| `paths` | object | Y | — | Access control; see below |
| `lifecycle` | object | N | `{always_on:false, idle_time_for_shutdown:60}` | See below |
| `minimum_portal_size` | string | N | `"xs"` | Enum: `xs \| s \| m \| l \| xl` |
| `store_info` | object | N per schema — **treat as required** | — | See below |

Schema `required` array is exactly:
`["v", "app_version", "name", "pretty_name", "icon", "entrypoints", "paths"]`.

**Version history:** v1.0 → v1.1 added `pretty_name`; v1.2 added `homepage` and `upstream_repo`.

> **`pretty_name` — agents.md says optional, the schema marks it required.** Follow the schema and
> always set it for new apps. `build_store_data.py` does tolerate its absence (falls back to
> `name.title()`), and legacy `v: "1.0"` apps such as immich omit it — but that is not a licence
> to omit it in new work.

> **`lifecycle` is genuinely optional.** The schema omits it from `required` and gives it the
> object default `{always_on:false, idle_time_for_shutdown:60}`. Omit the block for a plain web
> app; include it only to override. (An earlier revision of this digest recorded a docs table that
> marked `lifecycle` required — the current docs page uses numbered annotations and carries no
> such table, so that conflict no longer exists.)

> **`store_info` — schema says optional, tooling says required.** `build_store_data.py`
> `_make_metadata_entry` reads `app_meta['store_info']` with direct subscripting, so an app
> without it raises `KeyError` and the store build fails. Always provide it (at minimum
> `description_short`).

### `entrypoints[]`

| Field | Type | Req | Notes |
|---|---|---|---|
| `container_name` | string | Y | Must match `container_name` in compose template |
| `container_port` | integer | Y | Port the container listens on internally (plain HTTP) |
| `entrypoint_port` | string | Y | `"http"` (→ 443) or `"mqtt"` (→ 8883) |

At least one entrypoint required. MQTT entrypoints bypass access control entirely.

### `paths` (access control)

Object keyed by path prefix string. Empty string `""` is the required catch-all (evaluated last —
longest match wins). Per-entry: `access` (required, enum `public|private|peer`) and `headers`
(optional, string→string map; values may use template variables).

### `lifecycle`

| Field | Type | Notes |
|---|---|---|
| `always_on` | bool | Schema default `false`. `true` = never auto-stop; forbids `idle_time_for_shutdown` |
| `idle_time_for_shutdown` | int (seconds) | Inactivity before `docker-compose stop`. No own schema default; 60 comes from the `lifecycle` object default |

### `store_info`

| Field | Type | Notes |
|---|---|---|
| `description_short` | string | Required in practice; 1–2 sentences, fits app card |
| `description_long` | string or string[] | Optional; array = paragraphs |
| `hint` | string or string[] | Optional; array = bullets |
| `is_featured` | bool | Do not set — Freeshard team sets this (the docs' own example shows `true`; ignore that) |

---

## `docker-compose.yml.template` Rules

1. **Portal network**: Declare `portal` as external; every proxy-reachable container must join it.
2. **`container_name`**: Every service needs explicit `container_name`; main service must match `entrypoints[].container_name`.
3. **Naming convention**: Supporting services → `<app-name>-<service>` (e.g., `myapp-postgres`).
4. **Image tags**: Pin to exact version matching `app_version`. Never `latest`.
5. **`restart`**: Always `always` (or `unless-stopped`). Use `restart: no` only for one-shot init containers.
6. **Multi-service isolation**: Only the entrypoint container joins `portal`; create an app-private network for inter-service comms.
7. **Docker socket**: Mount read-only only: `/var/run/docker.sock:/var/run/docker.sock:ro`.
8. **Filesystem access**: Mount only paths provided by `fs.*` variables. Mounting `fs.all_app_data` requires justification.
9. **Resources**: Apps share the shard. Resource-heavy apps must declare `minimum_portal_size`.

### Minimal template

```yaml
networks:
  portal:
    external: true

services:
  my-app:
    restart: always
    image: org/my-app:1.0.0
    container_name: my-app
    volumes:
      - "{{ fs.app_data }}/data:/data"
    environment:
      - BASE_URL=https://my-app.{{ portal.domain }}
    networks:
      - portal
```

### Multi-service template (with DB + cache)

```yaml
networks:
  portal:
    external: true
  my-app:

services:
  my-app:
    restart: always
    image: org/my-app:1.0.0
    container_name: my-app
    depends_on: [my-app-postgres, my-app-redis]
    environment:
      - DATABASE_URL=postgres://myapp:myapp@my-app-postgres:5432/myapp
      - BASE_URL=https://my-app.{{ portal.domain }}
    networks: [portal, my-app]

  my-app-postgres:
    restart: always
    image: postgres:16
    container_name: my-app-postgres
    volumes:
      - "{{ fs.app_data }}/pgdata:/var/lib/postgresql/data"
    environment:
      - POSTGRES_USER=myapp
      - POSTGRES_PASSWORD=myapp
      - POSTGRES_DB=myapp
    networks: [my-app]

  my-app-redis:
    restart: always
    image: redis:7-alpine
    container_name: my-app-redis
    networks: [my-app]
```

---

## Template Variables

Rendered at install time via Jinja-like `{{ variable }}` syntax.

| Variable | Description | Example |
|---|---|---|
| `portal.domain` | Shard's FQDN | `8271dd.example.com` |
| `portal.id` | Full shard hash-ID | `8271dd...` (long) |
| `portal.short_id` | First 6 chars of shard ID | `8271dd` |
| `portal.public_key_pem` | Shard's public key (PEM) | `-----BEGIN PUBLIC KEY-----...` |
| `fs.app_data` | App-specific persistent storage | `/home/user/.freeshard/user_data/app_data/my-app` |
| `fs.all_app_data` | Parent of all app data dirs | `/home/user/.freeshard/user_data/app_data` |
| `fs.shared` | Cross-app shared data dir | `/home/user/.freeshard/user_data/shared` |
| `fs.installation_dir` | Installation files location | `/home/user/.freeshard/core/installed_apps/my-app` |

> `fs.installation_dir` is documented in the dev docs but still absent from agents.md.

Available in `paths[].headers` values only (not compose template):

| Variable | Values |
|---|---|
| `{{ auth.client_type }}` | `"terminal"` / `"peer"` / `"anonymous"` |
| `{{ auth.client_id }}` | Cryptographic client identifier |
| `{{ auth.client_name }}` | User-assigned client name |

Portal variables (`portal.*`) are also usable in headers values.

---

## Access Modes and Header Templating

### Access modes

| Mode | Who can access |
|---|---|
| `"private"` | Only paired devices (shard owner's terminals) |
| `"public"` | Anyone (no auth) |
| `"peer"` | Other shards added as peers (mutual peering required) |

Access control applies to HTTP entrypoints only. MQTT entrypoints have no AC.
Path matching: longest prefix wins; `""` is the required fallback.

Pairing detail: a paired *browser* holds a JWT cookie with a device ID and secret key, and gets
full access to the shard web UI and all apps. Unpaired visitors see only `public` paths.

Two sanctioned designs: **path-based AC** (split public/private by URL prefix) and **app-specific
AC** (everything forwarded, app decides using the injected `auth.*` headers).

### Common access patterns

**Fully private:**
```json
"paths": { "": { "access": "private" } }
```

**Auth-proxy (private + header):**
```json
"paths": { "": { "access": "private", "headers": { "X-Ptl-User": "admin" } } }
```

**Public (app manages own auth):**
```json
"paths": { "": { "access": "public" } }
```

**Mixed (private default, some paths public):**
```json
"paths": {
  "": { "access": "private" },
  "/share/": { "access": "public" },
  "/api/public/": { "access": "public" }
}
```

**Peer access (multi-shard app):**
```json
"paths": {
  "": { "access": "private" },
  "/api/peer/": {
    "access": "peer",
    "headers": {
      "X-Ptl-Client-Id": "{{ auth.client_id }}",
      "X-Ptl-Client-Type": "{{ auth.client_type }}"
    }
  }
}
```

---

## Lifecycle

| Scenario | Config |
|---|---|
| Simple web app | `idle_time_for_shutdown: 60` (default, omit lifecycle block) |
| Background processing | `idle_time_for_shutdown: 300` – `3600` |
| IoT / messaging (mosquitto, node-red) | `always_on: true` |
| Slow-starting app | Higher idle timeout to avoid churn |

**Lifecycle stages (from dev docs):**
1. Install: `docker-compose up --no-start` — images pulled, containers created, not running
2. Start: reverse proxy detects HTTP traffic, signals the core; splash screen (served by the shard
   core, auto-refreshing — the app does nothing) shown during startup
3. Stop: `docker-compose stop` after idle timeout (containers stopped, not removed; data persists)

---

## `minimum_portal_size` Classes

Shards run on **OVH only** (Azure is EOL for shard hosting). Size against OVH specs. **Bias toward
the smallest tier that runs** — better an app runs slowly than not at all; users can resize up.
Don't pad "to be safe".

| Value | OVH flavor / vCore / RAM | Use when |
|---|---|---|
| `"xs"` | d2-2 — 1 / 2 GB | Single lightweight process; no DB |
| `"s"` | d2-4 — 2 / 4 GB | **Default for most multi-process apps**, incl. a real DB, if idle stays under ~2 GB |
| `"m"` | d2-8 — 4 / 8 GB | Idle genuinely exceeds ~2–3 GB, or needs ≥4 cores |
| `"l"` | b3-16 — 4 / 16 GB | Large in-memory indexes / ML |
| `"xl"` | b3-32 — 8 / 32 GB | Most intensive |

**Source of truth:** freeshard-controller-backend `config.yml` → `ovhcloud.vm_sizes` and
`freeshard_controller/service/pricing.py`. Mirrored in KB `~/knowledge_base/freeshard/vm-sizes.md`.
> Re-verified 2026-09-28 against `freeshard-controller-backend/config.yml` → `ovhcloud.vm_sizes`:
> xs d2-2 1/2 GB €5.50, s d2-4 2/4 GB €11, m d2-8 4/8 GB €19.80, l b3-16 4/16 GB €51,
> xl b3-32 8/32 GB €102. Flavor and RAM mapping unchanged; prices are per month.

---

## Common Patterns

### Auth-proxy env vars by app family

| App | Env vars |
|---|---|
| linkding | `LD_ENABLE_AUTH_PROXY=True`, `LD_AUTH_PROXY_USERNAME_HEADER=HTTP_X_PTL_USER` |
| navidrome | `ND_REVERSEPROXYUSERHEADER=X-Ptl-User`, `ND_REVERSEPROXYWHITELIST=0.0.0.0/0` |
| paperless-ngx | `PAPERLESS_AUTO_LOGIN_USERNAME=admin` |

### Shared data paths

| Path | Used by |
|---|---|
| `{{ fs.shared }}/documents` | paperless-ngx |
| `{{ fs.shared }}/music` | navidrome |
| `{{ fs.shared }}/pictures` | immich, photoprism |
| `{{ fs.shared }}/media` | general media apps |

### Data persistence & migration

Each app gets its own `fs.app_data` dir; it starts empty and allows arbitrary read/write. Mounted
`fs.app_data` / `fs.shared` dirs survive app stop, restart, and version upgrades. **Migration is the
developer's responsibility:** on a version bump the app must detect data written by the old version
and migrate it — the shard does nothing automatically. (This is why stateful multi-image apps also
wire `upstream_compose_url`; see Update Flow.)

### Telemetry opt-out

Always disable telemetry/analytics via env vars. Each app has its own var — check upstream docs.
No platform-standard variable exists.

### Base URL pattern

```
BASE_URL=https://<name>.{{ portal.domain }}
```

---

## Update Flow

Updates run via the `/update-apps` skill, which orchestrates `update/update.py` and reasons over
breaking-change candidates. There is **no top-level `update.py`** — only `update/update.py`, with
`check` and `apply` subcommands. The old `check/skip/update/test/build/commit` CLI and its
`adapt_version_string` table are superseded by per-app `update_check.py` (no `adapt_version_string`
remains in `update/update.py` or `update/update_lib.py`; version rewriting is now a plain
`str.replace` over `*.yml.template`, `*.json`, `*.env` in `_replace_in_files()`).

1. `python3 update/update.py check --json` polls every `apps/<name>/update_check.py` in parallel,
   writes `update/update_info/latest_check.json`.
2. Skill classifies each outdated app: clean patch/minor, no "breaking" notes, no non-trivial
   upstream-compose change → AUTO; anything else → REVIEW.
3. `python3 update/update.py apply <app> <ver> --auto|--review --branch-ts <ts>` rewrites version
   strings, runs `docker compose pull --dry-run`, commits onto `updates/<iso-ts>`.
4. Skill opens a PR; the GH `preview` job builds and uploads `updated_apps.zip` and comments the URL.
5. User smoke-installs the bundle on a fresh shard, then merges.

### Per-app `update_check.py`

Every app folder has one, defining `def check(current_version: str) -> dict` returning:
`latest_version` (required), `release_notes_url`, `release_body`, `upstream_compose_url` (optional;
may contain a `{version}` placeholder).

Helpers in `update/update_lib.py`: `latest_github_release`, `latest_dockerhub_tag`,
`latest_ghcr_tag`, `latest_lscr_tag`. Unresolvable tag scheme → raise `NotImplementedError`
(reported as `error`). Manual-update apps → raise `update_lib.OptOut("<reason>")` (reported as
`opt_out`, reason preserved).

**Wire `upstream_compose_url` for stateful / multi-image apps.** The bumper only string-replaces the
app's own version, so a supporting image upstream bumps independently silently drifts in our frozen
template. With the URL set, `compose_diff` flags any change beyond the app-version bump → forces
REVIEW. Wired: immich, etherpad, paperless-ngx, titra.
**Blind spot:** the diff compares upstream's compose at the *old* and *new* version of the current
bump only. Drift introduced before that range stays invisible forever. When a supporting image looks
old, compare our template against upstream's compose directly.

### Smoke-testing

`uv run update/smoke_test.py <bundle>` assigns a throwaway trial shard, pairs, installs each app and
polls it. Gotchas: a 200 is not automatically a pass (Traefik's catch-all `PathPrefix("/")` router
makes *any* unknown subdomain answer 200 with the web terminal — the script fingerprints it); keep
`--poll-interval` under 5s (the shard's `RECENT_ACCESS_GRACE`); the owner email must be **routable**
(an unroutable one bricks the shard at first pairing).

Manual single-app checklist: bump `app_version`, bump the image tag in the template, update `.env`
if it pins a version, run `python -m build_store_data`.

---

## Internal Services (Shard Core API)

Apps can call the shard core REST API via Docker networking.

**Base URL:** `http://shard_core` · **Example:** `GET http://shard_core/protected/apps`

Full API reference: https://ptl.gitlab.io/portal_core/

**Security warning (verbatim from dev docs):** "Right now, the APIs described here are accessible
without any checks. Your app can view, modify, and delete critical information about the shard and
even completely break it."

**Inter-app APIs:** Not yet implemented; the docs description is aspirational.

---

## Peering (Multi-Shard / Federation)

> Not in agents.md — dev-docs only. **Feature currently deactivated** because no app in the store
> uses it.

**Concept:** Each shard has a globally unique alphanumeric ID (like a phone number). Owners add
other shard IDs to a contact list ("peers"). Both shards must add each other (mutual peering)
before communication succeeds.

**App developer responsibilities:**
- Query peers: `GET http://shard_core/protected/peers`
- Expose peer paths in `app_meta.json` with `"access": "peer"`
- Implement symmetric endpoints on both shards
- Manage app-specific peer metadata (ACLs, privileges) and the send/receive business logic
- Route outgoing calls through the core (adds signatures):
  `http://shard_core/internal/call_peer/<peer-id>/<path>`
  e.g. GET `foo/bar` on peer `b8rk3f` → `http://shard_core/internal/call_peer/b8rk3f/foo/bar`

**Auth:** Shard IDs provide end-to-end encrypted, authenticated messaging; no credential exchange.

---

## Events / MQTT Broker (Upcoming)

> **Not implemented.** Docs state: "Events are not yet implemented. You cannot use them yet and
> their implementation - when completed - might differ from this description." The page carries no
> code and no topic-namespace spec.

Planned: a built-in broker per shard publishing system-wide events; an app may subscribe to any
topic and publish under an app-specific namespace.

**Current MQTT entrypoints** are unrelated: `entrypoint_port: "mqtt"` exposes port 8883 (TLS) for
external clients. Mosquitto is an installable app, not a built-in service — external clients hit
`mosquitto.<shard-id>.<domain>:8883`, WebSocket clients use 443, internal apps (Node-RED, Home
Assistant) reach `mosquitto:1883` over the portal network.

---

## Integration Levels (from dev docs)

| Level | Description |
|---|---|
| 1 — Blocked | No Docker image, external service deps, or specific hardware required |
| 2 — Usable with caveats | Runs, but rough UX (e.g. a needless account-creation/login screen). Requires: fully containerised, only internal deps, zero manual setup after first start, modest resources |
| 3 — Generally adapted | Smooth single-user experience, no needless auth, clean public/private path split |
| 4 — Specifically adapted | Leverages peering for multi-user features |

Target Level 3 for all new submissions. Level 4 requires peering (currently deactivated).

Workflow: verify Level 2 compliance → write the compose template → write `app_meta.json` → test on
a real shard → add proxy auth / access control.

---

## App Store Submission

1. Fork `https://github.com/FreeshardBase/app-repository`
2. Add folder `apps/<your-app>/` with `app_meta.json`, `docker-compose.yml.template`, icon
3. Branch name: `app/<your-app>`
4. Open PR; "you may not modify any other apps except your own"
5. Do not set `is_featured`
6. For version updates: update the app's files and open another PR

Custom/sideloaded install (dev testing): ZIP the app folder — the ZIP name must exactly match
`app_meta.json` `name`. Upload via shard UI → Apps → "Tools for app developers" → "Install Custom
App"; it then installs as if it came from the store. The ZIP holds only config, not images, so it is
tiny and can be emailed to others to test.

**Sidecar files are supported — the folder is NOT limited to the 3 standard files.**
`build_store_data.py` (`make_app_zips`) zips EVERY file in the app folder recursively
(`app_path.glob('**/*')`, skipping only directories and the zip itself). Ship any config file —
`Caddyfile`, `nginx.conf`, ClickHouse `config.d/*.xml`, a `.env` — and it extracts next to the
rendered compose on the shard (= `{{ fs.installation_dir }}`). Reference shipped files two ways:
- `env_file:` / `${VAR}` substitution — precedent `apps/immich/.env` (verified present).
- bind-mount read-only: `{{ fs.installation_dir }}/<file>:/path/in/container:ro`.

Caveat: sidecar files ship verbatim — only `docker-compose.yml.template` goes through `{{ }}`
rendering, so a sidecar cannot contain template vars. Do NOT reach for `command:` heredoc config
injection; this mechanism already exists.

---

## Revenue Share

Part of each user's monthly subscription is a flat app payment (docs example: 3.00 €). The shard
tracks which apps are installed and for how long during the month, converts that into per-app
weights, splits the flat fee by weight, and sums each app's share across all shards into the
developer's account (withdrawable any time or auto-paid to a bank account). User-driven manual
boosting of favourite apps is described but unreleased. Users pay the same flat fee regardless of
app count, so installing more apps costs them nothing.

---

## New Concepts from Dev Docs Not in agents.md

| Concept | Summary |
|---|---|
| `fs.installation_dir` | Additional template var pointing to install-time files dir |
| Internal services API warning | No auth checks on shard core; apps have full destructive access |
| Inter-app APIs | Planned but not implemented |
| Events/MQTT broker | Built-in broker planned; not implemented; app-namespace topic scoping planned |
| Integration levels 1–4 | Formal taxonomy for how well an app is adapted to the platform |
| Peering / `call_peer` API | Cross-shard communication via shard core proxy; currently deactivated |
| Revenue share | Monthly flat-fee split proportional to install duration |
| Mutual peering requirement | Both shards must add each other before peer access works |
| Splash screen on cold start | Shown by the shard core automatically during container startup |
| `docker-compose up --no-start` | How the shard installs apps (containers created but not started) |
| Single-user isolation | One VM per owner; sharing is P2P per-item, never multi-tenant accounts |
