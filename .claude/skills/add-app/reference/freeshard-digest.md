# Freeshard App-Integration Reference Digest

> Sources: agents.md (primary) + docs.freeshard.net developer docs (crawled 2026-07-07).
> Where they disagree this digest notes which source wins and why.

---

## App Model

An app is a Docker Compose project installed onto a user's shard (single-tenant VM). The shard:
- Renders the `docker-compose.yml.template` at install time (variable substitution)
- Uses `app_meta.json` to configure its reverse proxy, lifecycle manager, and app store display
- Routes HTTP traffic via subdomain: `<app-name>.<shard-id>.<domain>` → app container port
- Routes MQTT traffic on port 8883 (no access control; raw TLS termination only)
- Provides a splash screen while containers start on first request

**Fundamental constraints from dev docs:**
- One container must serve HTTP (not HTTPS) on a configured port
- UI must be responsive (notebook / tablet / smartphone)
- No external SaaS dependencies; only internal shard services
- No manual post-install configuration required; apps must self-configure on first start

---

## `app_meta.json` Schema

Schema URL: `https://storageaccountportab0da.blob.core.windows.net/json-schema/0-30-2/schema_app_meta_1.2.json`

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
| `lifecycle` | object | N* | `{always_on:false, idle_time_for_shutdown:60}` | See below |
| `minimum_portal_size` | string | N | `"xs"` | Enum: `xs \| s \| m \| l \| xl` |
| `store_info` | object | Y | — | App store display; see below |

**Version history:** v1.0 → v1.1 added `pretty_name`; v1.2 added `homepage` and `upstream_repo`.

> **agents.md marks `pretty_name` as optional; the JSON schema marks it required.** Follow the schema — mark `pretty_name` as required.

> **`lifecycle` — docs disagree.** The `app_meta.json` docs table marks `lifecycle` (and both its inner fields) as required; agents.md marks it optional with a documented default. **agents.md wins in practice:** 4 of the 42 repo apps omit the block entirely and the shard applies the default (`always_on:false`, `idle_time_for_shutdown:60`). Omit `lifecycle` for a plain web app; include it only to override the default.

> **`store_info` — treat as required.** The docs schema table marks it optional, but all 42 repo apps include it and agents.md marks it required. Always provide it (at minimum `description_short`).

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
| `headers` | object | N | Key→value; values may use template variables (see below) |

### `lifecycle`

| Field | Type | Notes |
|---|---|---|
| `always_on` | bool | `true` = never auto-stop; mutually exclusive with `idle_time_for_shutdown` |
| `idle_time_for_shutdown` | int (seconds) | Inactivity before `docker-compose stop`; default 60 |

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
8. **Filesystem access**: Mount only paths provided by `fs.*` variables. Mounting `fs.all_app_data` requires justification.

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

Path matching: longest prefix wins; `""` is required fallback.

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

**Lifecycle stages (from dev docs):**
1. Install: `docker-compose up --no-start` — containers created, not running
2. Start: reverse proxy detects HTTP traffic → starts containers; splash screen shown during startup
3. Stop: `docker-compose stop` after idle timeout (containers halted, not removed; data persists)

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

`update.py` automates version bumping for apps with `upstream_repo` set (GitHub releases only).

```
python update.py check    # Check for new GitHub releases
python update.py skip <app1> <app2>  # Skip specific apps
python update.py update   # Write new version strings
python update.py test     # Verify Docker images pullable
python update.py build    # Rebuild zips
python update.py commit   # Branch + per-app commits + merge
```

Manual update checklist:
1. Update `app_version` in `app_meta.json`
2. Update image tag in `docker-compose.yml.template`
3. Update `.env` if it contains version pins
4. Run `python -m build_store_data`

### `adapt_version_string` — known entries

| App(s) | Transform |
|---|---|
| actual, audiobookshelf, drawio, etherpad, kavita, linkding, navidrome, paperless-ngx, stirling-pdf, grist, memos | Strip leading `v` |
| element | Strip suffix after `-` |
| glances | Append `-full` |

---

## Internal Services (Shard Core API)

Apps can call the shard core REST API via Docker networking.

**Base URL:** `http://shard_core`

**Example:** `GET http://shard_core/protected/apps` — list all installed apps

Full API reference: https://ptl.gitlab.io/portal_core/

**Security warning (from dev docs):** These APIs are currently accessible without auth checks. An app can read, modify, or delete critical shard data. Treat with care.

**Inter-app APIs:** Not yet implemented. Description in docs is aspirational; do not rely on it.

---

## Peering (Multi-Shard / Federation)

> New concept not in agents.md — documented in dev docs. Feature currently disabled pending real-world implementations.

**Concept:** Each shard has a globally unique ID. Owners add other shard IDs to a contact list ("peers"). Both shards must add each other (mutual peering) before communication succeeds.

**App developer responsibilities:**
- Query shard core for known peers before communicating: `GET http://shard_core/protected/peers`
- Expose peer-accessible paths in `app_meta.json` with `"access": "peer"`
- Implement symmetric endpoints on both shards (each peer call needs a matching handler on the other side)
- Route outgoing peer calls through the shard core (adds auth signatures):
  ```
  http://shard_core/internal/call_peer/<peer-id>/<path>
  ```
  e.g. GET `foo/bar` on peer `b8rk3f` → `http://shard_core/internal/call_peer/b8rk3f/foo/bar`

**Auth:** Shard IDs themselves provide end-to-end encrypted, authenticated messaging. No separate credential exchange needed.

**Use case:** Multi-user apps (chat, collaboration) that remain single-user-isolated but communicate across shards.

---

## Events / MQTT Broker (Upcoming)

> Feature not yet implemented. Details below are from dev docs aspirational description only.

**Built-in event broker:** Each shard will have an MQTT-based event broker. Apps will be able to subscribe to any topic and publish under an app-specific namespace.

**Current MQTT entrypoints:** The `"mqtt"` entrypoint_port exposes port 8883 externally (TLS) for external MQTT clients. Internal app-to-app MQTT (events) is a separate, not-yet-implemented system.

**Mosquitto (external IoT use case):** Mosquitto is an installable app (not a built-in service). For IoT:
- External MQTT clients connect to `mosquitto.<shard-id>.<domain>:8883`
- WebSocket clients use port 443
- Internal apps (Node-RED, Home Assistant) connect to `mosquitto:1883` via portal network
- Client/ACL management via Cedalo Management Center (bundled with Mosquitto app)

---

## Integration Levels (from dev docs)

| Level | Description |
|---|---|
| 1 — Blocked | No Docker image, external service deps, or specific hardware required |
| 2 — Usable with caveats | Functional but rough UX; unnecessary login screens, etc. |
| 3 — Generally adapted | Proxy auth enabled, clean public/private path split |
| 4 — Specifically adapted | Leverages peering for multi-user features |

Target Level 3 for all new app submissions. Level 4 requires peering (currently disabled).

---

## App Store Submission

1. Fork `https://github.com/FreeshardBase/app-repository`
2. Add folder `apps/<your-app>/` with `app_meta.json`, `docker-compose.yml.template`, icon
3. Branch name: `app/<your-app>`
4. Open PR; do not modify other apps' folders
5. Do not set `is_featured`
6. For version updates: new PR on same branch convention

Custom/sideloaded install (dev testing): ZIP the files — `app_meta.json`, `docker-compose.yml.template`, and icon (icon optional) — the ZIP name must exactly match `app_meta.json` `name`. Upload via shard UI → Apps → "Tools for app developers" → "Install Custom App"; it then installs as if submitted to the store. The ZIP holds only config (not the images), so it's tiny and can be emailed to others to test.

---

## New Concepts from Dev Docs Not in agents.md

| Concept | Summary |
|---|---|
| `fs.installation_dir` | Additional template var pointing to install-time files dir |
| Internal services API warning | No auth checks on shard core; apps have full destructive access |
| Inter-app APIs | Planned but not implemented |
| Events/MQTT broker | Built-in broker planned; not implemented; app-namespace topic scoping planned |
| Integration levels 1–4 | Formal taxonomy for how well an app is adapted to the platform |
| Peering / `call_peer` API | Mechanism for cross-shard communication via shard core proxy |
| Revenue share | Monthly flat-fee split proportional to install duration; developer payout model |
| Mutual peering requirement | Both shards must add each other before peer access works |
| Splash screen on cold start | Shown by shard UI automatically during container startup |
| `docker-compose up --no-start` | How the shard installs apps (containers created but not started) |
