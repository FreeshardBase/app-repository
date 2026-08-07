# Freeshard App-Integration Reference Digest

> Sources: agents.md (primary) + docs.freeshard.net developer docs (crawled 2026-08-07).
> Where they disagree this digest notes which source wins and why.

---

## App Model

An app is a Docker Compose project installed onto a user's shard (single-tenant VM). The shard:
- Renders the `docker-compose.yml.template` at install time (variable substitution)
- Uses `app_meta.json` to configure its reverse proxy, lifecycle manager, and app store display
- Routes HTTP traffic via subdomain: `<app-name>.<shard-id>.<domain>` → app container port
- Routes MQTT traffic on port 8883 (no access control; raw TLS termination only)
- Manages TLS itself — one cert covers all subdomains, so apps never handle TLS
- Provides a splash screen while containers start on first request

**Fundamental constraints from dev docs:**
- One container must serve HTTP (not HTTPS) on a configured port
- UI must be responsive (notebook / tablet / smartphone)
- No external SaaS dependencies; only internal shard services
- No manual post-install configuration required; apps must self-configure on first start
- Images must be on Docker Hub or a comparable public registry
- Modest resource footprint; any language/framework is fine

---

## `app_meta.json` Schema

Schema URL: `https://storageaccountportab0da.blob.core.windows.net/json-schema/0-30-2/schema_app_meta_1.2.json`

### Root fields

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| `v` | string | Y | — | Format version. Use `"1.2"` for new apps |
| `app_version` | string | Y | — | Must match Docker image tag |
| `name` | string | Y | — | Lowercase, `[a-z0-9-]` only; must match folder name; becomes subdomain; unique across the store |
| `pretty_name` | string | Y | — | Display name (v1.1+) |
| `icon` | string | Y | — | Filename in app folder; PNG / JPEG / SVG |
| `homepage` | string | N | — | App homepage URL (v1.2+) |
| `upstream_repo` | string | N | — | GitHub repo URL for auto-update checking (v1.2+) |
| `entrypoints` | array | Y | — | See below |
| `paths` | object | Y | — | Access control; see below |
| `lifecycle` | object | N* | `{always_on:false, idle_time_for_shutdown:60}` | See below |
| `minimum_portal_size` | string | N | `"xs"` | Enum: `xs \| s \| m \| l \| xl` |
| `store_info` | object | Y* | — | App store display; see below |

**Version history:** v1.0 → v1.1 added `pretty_name`; v1.2 added `homepage` and `upstream_repo`.

> **`pretty_name` — docs table says optional, JSON schema `required` array includes it.** Follow the schema: always set it.

> **`lifecycle` — docs disagree.** The `app_meta.json` docs table marks it optional (no default listed); the JSON schema gives it the default `{always_on:false, idle_time_for_shutdown:60}`. **Omission is fine:** 4 of the 40 repo apps omit the block entirely. Omit `lifecycle` for a plain web app; include it only to override the default.

> **`store_info` — treat as required.** Both the docs table and the JSON schema mark it optional, but all 40 repo apps include it, agents.md marks it required, and the submission page demands at least `description_short`. Always provide it.

### `entrypoints[]`

| Field | Type | Req | Notes |
|---|---|---|---|
| `container_name` | string | Y | Must match `container_name` in compose template |
| `container_port` | integer | Y | Port the container listens on internally (plain HTTP) |
| `entrypoint_port` | string | Y | `"http"` (→ 443 externally) or `"mqtt"` (→ 8883 externally) |

At least one entrypoint required. MQTT entrypoints bypass access control entirely.

### `paths` (access control)

Object keyed by path prefix string. Empty string `""` is required catch-all (evaluated last — longest match wins).

| Field | Type | Req | Notes |
|---|---|---|---|
| `access` | string | Y | `"public"` \| `"private"` \| `"peer"` |
| `headers` | object | N | Key→value, values are strings; may use template variables (see below) |

### `lifecycle`

| Field | Type | Notes |
|---|---|---|
| `always_on` | bool | `true` = never auto-suspend; mutually exclusive with `idle_time_for_shutdown` |
| `idle_time_for_shutdown` | int (seconds) | Inactivity before the shard suspends the app; default 60 |

### `store_info`

| Field | Type | Notes |
|---|---|---|
| `description_short` | string | Required for store listing; 1–2 sentences, fits app card |
| `description_long` | string or string[] | Optional; array = paragraphs |
| `hint` | string or string[] | Optional; array = bullets |
| `is_featured` | bool | Do not set — Freeshard team sets this |

---

## `docker-compose.yml.template` Rules

1. **Portal network**: Declare `portal` as external; every proxy-reachable container must join it.
2. **`container_name`**: Every service needs explicit `container_name`; main service must match `entrypoints[].container_name`.
3. **Naming convention**: Supporting services → `<app-name>-<service>` (e.g., `myapp-postgres`).
4. **Image tags**: Pin to exact version matching `app_version`. Never `latest`.
5. **`restart`**: Always `always` (or `unless-stopped`). Use `restart: no` only for one-shot init containers.
6. **Multi-service isolation**: Only the entrypoint container joins `portal`; create an app-private network for inter-service comms.
7. **Docker socket**: Mount read-only only: `/var/run/docker.sock:/var/run/docker.sock:ro`.
8. **Filesystem access**: Mount only paths provided by `fs.*` variables — no other host directories. Mounting `fs.all_app_data` requires justification.

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

> `fs.installation_dir` is documented in the dev docs but absent from agents.md. Included here from the dev docs.

Available in `paths[].headers` values only (not compose template):

| Variable | Values |
|---|---|
| `{{ auth.client_type }}` | `"terminal"` / `"peer"` / `"anonymous"` |
| `{{ auth.client_id }}` | Cryptographic client identifier (e.g. `eie767`) |
| `{{ auth.client_name }}` | User-assigned client name (e.g. `my notebook`) |

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

Path matching: prefixes evaluated longest → shortest, first match wins; `""` is the required fallback.

### Common access patterns

**Fully private:**
```json
"paths": { "": { "access": "private" } }
```

**Auth-proxy (private + header):**
```json
"paths": {
  "": {
    "access": "private",
    "headers": { "X-Ptl-User": "admin" }
  }
}
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

**Lifecycle stages (dev docs `lifecycle/` page):**
1. Install: `docker-compose up --no-start` — containers created, not running
2. Start: reverse proxy detects HTTP traffic → starts containers; splash screen shown during startup (handled by shard core)
3. Stop: `docker-compose stop` after idle timeout (containers halted, not removed; data persists)

**Current implementation is three-state (blog 2026-07-25, `putting-apps-to-sleep-…`; the `lifecycle/` docs page is not yet updated):**
1. **Running** — normal
2. **Paused + paged** — idle apps get `docker compose pause` (cgroup freezer) plus `memory.reclaim` to push anon pages to swap; wake is a single `docker compose unpause`, under 2 s, no cold start
3. **Stopped** — cold shutdown under memory pressure (PSI-driven demotion); 30 s+ wake

Developer-facing config is unchanged (`always_on` / `idle_time_for_shutdown` still the only knobs). Practical consequence: an app that misbehaves when its process group is frozen mid-request (long-lived timers, external keepalives, in-flight DB transactions) is now the failure case to watch for, not slow cold starts. A slow-starting app is a weaker argument for a high idle timeout than it used to be.

---

## `minimum_portal_size` Classes

Shards run on **OVH only** (Azure is EOL for shard hosting). Size against OVH specs. **Bias toward the smallest tier that runs** — better an app runs slowly than not at all; users can resize up. Don't pad "to be safe".

| Value | OVH flavor / vCore / RAM | Use when |
|---|---|---|
| `"xs"` | d2-2 — 1 / 2 GB | Single lightweight process; no DB |
| `"s"` | d2-4 — 2 / 4 GB | **Default for most multi-process apps**, incl. a real DB, if idle stays under ~2 GB (e.g. Node + MongoDB + search) |
| `"m"` | d2-8 — 4 / 8 GB | Idle genuinely exceeds ~2–3 GB, or needs ≥4 cores |
| `"l"` | b3-16 — 4 / 16 GB | Large in-memory indexes / ML |
| `"xl"` | b3-32 — 8 / 32 GB | Most intensive |

**Source of truth:** freeshard-controller-backend `config.yml` → `ovhcloud.vm_sizes` (flavor mapping, specs in inline comments) and `freeshard_controller/service/pricing.py` (prices). Mirrored in KB `~/knowledge_base/freeshard/vm-sizes.md` (which lists every sync location). If these tiers change upstream, re-sync both this table and that note.

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

Mounted `fs.app_data` / `fs.shared` dirs survive app stop, restart, and version upgrades; an app_data dir starts empty on install. **Migration is the developer's responsibility:** on a version bump the app must detect data written by the old version and migrate it if the new version needs a different layout — the shard does nothing automatically. (This is why stateful multi-image apps also wire `upstream_compose_url`; see Update Flow.)

### Telemetry opt-out

Always disable telemetry/analytics via env vars. Each app has its own var — check upstream docs. No platform-standard variable exists.

### Base URL pattern

```
BASE_URL=https://<name>.{{ portal.domain }}
```

---

## Update Flow

Repo-side, driven by the `/update-apps` skill (`.claude/skills/update-apps/`) over `update/update.py`. **agents.md is authoritative here; the dev docs say nothing about this.**

```
python3 update/update.py check --json                                  # poll every apps/<name>/update_check.py in parallel
python3 update/update.py apply <app> <ver> --auto|--review --branch-ts <ts>
```

`check` writes `update/update_info/latest_check.json`. The skill classifies each outdated app: clean patch/minor, no "breaking" notes, no non-trivial upstream-compose change → AUTO; anything else → REVIEW. `apply` rewrites version strings, runs `docker compose pull --dry-run`, and commits onto `updates/<iso-ts>` with message `update <app> from <old> to <new> [AUTO|REVIEW]`. The skill opens a PR; a GH `preview` job builds `updated_apps.zip` for smoke-install on a fresh shard before merge.

### Per-app `update_check.py`

Every app folder has one, defining `def check(current_version: str) -> dict`:

| Key | Req | Notes |
|---|---|---|
| `latest_version` | Y | Must match the docker tag format |
| `release_notes_url` | N | — |
| `release_body` | N | Release-notes text, scanned for "breaking" |
| `upstream_compose_url` | N | Raw upstream compose URL, may contain `{version}` |

**Wire `upstream_compose_url` for stateful / multi-image apps.** The bumper only string-replaces the app's own version, so an independently-bumped supporting image (postgres, redis, vector extension) silently drifts in our frozen template. With the URL set, `compose_diff` compares upstream compose at old vs new version and forces REVIEW on any change beyond the app-version bump. Only wire it for upstreams that publish a version-pinned compose.

Wired: immich, etherpad, paperless-ngx, titra. Not wired: affine (mutable `:stable`), joplin-server (`OptOut`), overleaf (no version-pinned compose), photoprism (date-stamp tags).

Helpers in `update/update_lib.py`: `latest_github_release`, `latest_dockerhub_tag`, `latest_ghcr_tag`, `latest_lscr_tag`. No resolvable tag pattern → raise `NotImplementedError` (reported as `error`). Manual-update-only apps (self-built images like mosquitto; unreliable tags like joplin-server) → raise `update_lib.OptOut("<reason>")` (reported as `opt_out`, reason preserved).

Manual checklist for a one-off bump: update `app_version` in `app_meta.json`, update the image tag in the compose template, update `.env` if it pins a version, run `python -m build_store_data`.

---

## Internal Services (Shard Core API)

Apps can call the shard core REST API via Docker networking.

**Base URL:** `http://shard_core`

**Example:** `GET http://shard_core/protected/apps` — list all installed apps

Full API reference: https://ptl.gitlab.io/portal_core/

**Security warning (from dev docs):** These APIs are currently accessible without auth checks. An app can read, modify, or delete critical shard data — or break the shard entirely. Hardening is promised but not shipped. Treat with care.

**Inter-app APIs:** Not yet implemented. Description in docs is aspirational; do not rely on it.

---

## Peering (Multi-Shard / Federation)

> New concept not in agents.md — documented in dev docs. Feature currently disabled: no app store app uses it, so it is switched off to avoid confusing users.

**Concept:** Each shard has a globally unique ID. Owners add other shard IDs to a contact list ("peers"). Both shards must add each other (mutual peering) before communication succeeds.

**App developer responsibilities:**
- Query shard core for known peers before communicating: `GET http://shard_core/protected/peers`
- Expose peer-accessible paths in `app_meta.json` with `"access": "peer"` (optionally forwarding peer id/name headers)
- Implement symmetric endpoints on both shards (each peer call needs a matching handler of the same method/path on the other side)
- Handle app-level ACLs/privileges yourself — the platform only authenticates the peer
- Route outgoing peer calls through the shard core (adds auth signatures):
  ```
  http://shard_core/internal/call_peer/<peer-id>/<path>
  ```
  e.g. GET `foo/bar` on peer `b8rk3f` → `http://shard_core/internal/call_peer/b8rk3f/foo/bar`

**Auth:** Shard IDs themselves provide end-to-end encrypted, authenticated messaging. No separate credential exchange needed.

**Use case:** Multi-user apps (chat, collaboration) that remain single-user-isolated but communicate across shards.

---

## Events / MQTT Broker (Upcoming)

> Feature not yet implemented; docs state the eventual implementation may differ from the description. No ports, topic-namespace format, or connection parameters are documented.

**Built-in event broker:** Each shard will publish system-wide events to a built-in broker. Apps will be able to subscribe to topics and publish under an app-specific namespace.

**Current MQTT entrypoints:** The `"mqtt"` entrypoint_port exposes port 8883 externally (TLS) for external MQTT clients. Internal app-to-app MQTT (events) is a separate, not-yet-implemented system.

**Mosquitto (external IoT use case):** Mosquitto is an installable app (not a built-in service). For IoT:
- External MQTT clients connect to `mosquitto.<shard-id>.<domain>:8883`
- WebSocket clients use port 443
- Internal apps (Node-RED, Home Assistant) connect to `mosquitto:1883` via portal network
- Client/ACL management via Cedalo Management Center (bundled with Mosquitto app)

---

## Integration Levels (from dev docs)

| Level | Description | Gate |
|---|---|---|
| 1 — Blocked | Cannot run: no Docker image, external service deps, or specific hardware required | — |
| 2 — Usable with caveats | Runs, rough UX (unnecessary login screens, public resources unreachable) | Whole app (backend + web UI) in docker images; depends only on services freeshard offers; no manual setup after first start; modest resource demands |
| 3 — Generally adapted | Mostly smooth single-user experience | Account creation / login eliminated (user management disabled or proxy auth); HTTP paths cleanly split public vs protected so path-based AC works |
| 4 — Specifically adapted | Uses freeshard-specific features (peering) for multi-user scenarios | Peering (currently disabled) |

Target Level 3 for all new app submissions.

**Adaptation workflow:** verify Level 2 → write/modify `docker-compose.yml.template` → write `app_meta.json` → test on a personal shard → add proxy auth and path AC.

---

## App Store Submission

1. Fork `https://github.com/FreeshardBase/app-repository`
2. Add folder `apps/<your-app>/` with `app_meta.json`, `docker-compose.yml.template`, icon
3. Branch name: `app/<your-app>`
4. Open PR; do not modify other apps' folders
5. Do not set `is_featured`
6. Provide at least `store_info.description_short`
7. For version updates: new PR on same branch convention

Repo-side scaffolding (agents.md): `just new-app <name>` copies `inactive_apps/template/`; fill in `$$edit$$` placeholders; `python -m build_store_data` builds the zip and `store_metadata.json`. Researched-but-rejected candidates get a file in `blocked_apps/` (schema in `blocked_apps/README.md`).

Custom/sideloaded install (dev testing): ZIP the app folder — the ZIP name must exactly match `app_meta.json` `name`. Upload via shard UI → Apps → developer-tools menu → "Install Custom App"; it then installs as if submitted to the store. The ZIP holds only config (not the container images), so it's tiny and can be emailed to others to test.

**Sidecar files are supported — the folder is NOT limited to the 3 standard files.** `build_store_data.py` (`make_app_zips`) zips EVERY file in the app folder recursively (`app_path.glob('**/*')`). Ship any config file — `Caddyfile`, `nginx.conf`, ClickHouse `config.d/*.xml`, a `.env` — alongside `app_meta.json` / the compose template / icon, and it extracts next to the rendered compose on the shard (= `{{ fs.installation_dir }}`). Reference shipped files two ways:
- `env_file:` / `${VAR}` substitution — precedent `apps/immich/.env` (documented in `agents.md` folder layout as an optional file).
- bind-mount read-only into a container: `{{ fs.installation_dir }}/<file>:/path/in/container:ro`.

Caveat: sidecar files are shipped verbatim — only `docker-compose.yml.template` is run through Freeshard's `{{ }}` template rendering, so a sidecar cannot contain template vars. Do NOT reach for `command:` heredoc config injection; this mechanism already exists.

---

## New Concepts from Dev Docs Not in agents.md

| Concept | Summary |
|---|---|
| `fs.installation_dir` | Additional template var pointing to install-time files dir |
| Shard-managed TLS | One cert per shard covers all app subdomains; apps serve plain HTTP |
| Internal services API warning | No auth checks on shard core; apps have full destructive access |
| Inter-app APIs | Planned but not implemented |
| Events/MQTT broker | Built-in broker planned; not implemented; app-namespace topic scoping planned |
| Integration levels 1–4 | Formal taxonomy for how well an app is adapted to the platform |
| Peering / `call_peer` API | Mechanism for cross-shard communication via shard core proxy |
| Mutual peering requirement | Both shards must add each other before peer access works |
| Revenue share | Part of each monthly subscription is a flat app-payment pool, split across installed apps by share of install time that month, summed across shards into the developer's account; user-adjustable weights are an upcoming feature |
| Splash screen on cold start | Shown by shard UI automatically during container startup |
| `docker-compose up --no-start` | How the shard installs apps (containers created but not started) |
| Pause + page-out idle state | Idle apps are frozen and swapped rather than stopped; sub-2 s wake (blog 2026-07-25) |
| `app_template` (dev-docs page) | Python/FastAPI+TinyDB scaffold on GitLab for writing a freeshard-native app from scratch — irrelevant when packaging an existing upstream image, which is what this repo does |
