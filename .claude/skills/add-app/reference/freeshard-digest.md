# Freeshard App Integration Model — Reference Digest

> **Source note:** `docs.freeshard.net` developer-doc sub-pages return HTTP 404 (only root and `/overview/` respond). All technical detail below is sourced from `agents.md` in the app-repository root, supplemented by live app examples (immich, linkding, navidrome, paperless-ngx, mosquitto, dozzle, etc.). The overview page confirmed the high-level model (Docker images, subdomain routing, single-user per shard) and was consistent with agents.md; no discrepancies found.

---

## App Model

Each app lives at `apps/<name>/` in the repository. An app is one or more Docker containers deployed via a `docker-compose.yml.template`. The app is reachable at `<name>.<shard-domain>` (HTTPS, port 443) via the shard's reverse proxy.

Key properties:
- Single-user per shard instance — no multi-tenancy, no user management required.
- Subdomain routing: `<app-name>.<shard-domain>` → proxied to `container_name:container_port`.
- All containers join the `portal` Docker network (shared with the reverse proxy and shard services).
- Internal (non-entrypoint) containers join an app-private network only.
- Ports are never exposed to the host; routing is proxy-only.

**Entrypoint ports:**

| `entrypoint_port` | Maps to external port |
|---|---|
| `"http"` | 443 (HTTPS) |
| `"mqtt"` | 8883 (MQTTS) |

---

## `app_meta.json` Schema

Format version: use `"v": "1.2"` for new apps (adds `homepage`, `upstream_repo`). `"1.1"` and `"1.0"` are legacy.

```jsonc
{
  "v": "1.2",                           // required. "1.0"|"1.1"|"1.2"
  "app_version": "1.0.0",               // required. Must match image tag in template.
  "name": "my-app",                     // required. Lowercase, letters/numbers/dashes. Matches folder name. Becomes subdomain.
  "pretty_name": "My App",              // optional. Display name. Defaults to titlecased name.
  "icon": "icon.svg",                   // required. Filename; must exist in app folder. SVG preferred.
  "homepage": "https://example.com",    // optional (v1.2+). App homepage URL.
  "upstream_repo": "https://github.com/org/repo", // optional (v1.2+). GitHub repo; enables auto-update via update.py.

  "entrypoints": [                      // required. At least one.
    {
      "container_name": "my-app",       // must match container_name in docker-compose.yml.template.
      "container_port": 8080,           // port the container listens on internally.
      "entrypoint_port": "http"         // "http" (→443) or "mqtt" (→8883).
    }
  ],

  "paths": {                            // required. Access control by path prefix.
    "": { ... },                        // required catch-all (empty string = all paths). Longest match wins.
    "/public/": { ... }                 // optional more-specific prefixes.
  },

  "lifecycle": {                        // optional.
    "always_on": false,                 // true = never auto-stop. Mutually exclusive with idle_time_for_shutdown.
    "idle_time_for_shutdown": 60        // seconds of no HTTP traffic before auto-stop. Default: 60.
  },

  "minimum_portal_size": "s",          // optional. Omit = "xs" (default). See size classes below.

  "store_info": {                       // required.
    "description_short": "One-line description.",
    "description_long": ["Paragraph 1.", "Paragraph 2."],  // optional. Array of strings or single string.
    "hint": ["Usage tip."],             // optional. Array of hint strings shown to user.
    "is_featured": false                // optional. Whether to highlight in app store.
  }
}
```

### `paths` entry schema

```jsonc
"<prefix>": {
  "access": "private",   // required. "private"|"public"|"peer"
  "headers": {           // optional. Headers injected into proxied requests.
    "X-Ptl-User": "admin",
    "X-Ptl-Client-Id": "{{ auth.client_id }}"
  }
}
```

---

## `docker-compose.yml.template` Rules

Templates use Jinja-like `{{ variable }}` syntax, replaced at installation time.

### Mandatory rules

1. **`portal` network**: Every template must declare it as `external: true`. Every container reachable by the proxy or other apps must join it.
2. **`container_name`**: Every service must have an explicit `container_name`. Main service's name must match `entrypoints[].container_name` in `app_meta.json`.
3. **Supporting service names**: Use `<app-name>-<service>` (e.g., `paperless-redis`, `affine-postgres`).
4. **`restart`**: Always `always` (or `unless-stopped`). Use `restart: no` only for one-shot init/migration containers.
5. **Image tags**: Pin to a specific version matching `app_version`. Never use `latest`.
6. **Private networks**: For multi-service apps, only the entrypoint container joins `portal`. Create an additional app-private network (named after the app) for internal services. Entrypoint joins both; supporting services join only the private network.

### Minimal single-container template

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

### Multi-service template (entrypoint + private network)

```yaml
networks:
    portal:
        external: true
    my-app:           # private network; no config needed

services:
    my-app:
        restart: always
        image: org/my-app:1.0.0
        container_name: my-app
        depends_on: [my-app-postgres, my-app-redis]
        networks: [portal, my-app]   # joins both

    my-app-postgres:
        restart: always
        image: postgres:16
        container_name: my-app-postgres
        volumes:
        - "{{ fs.app_data }}/pgdata:/var/lib/postgresql/data"
        networks: [my-app]           # private only

    my-app-redis:
        restart: always
        image: redis:7-alpine
        container_name: my-app-redis
        networks: [my-app]
```

### Special mounts

- Docker socket (read-only): `/var/run/docker.sock:/var/run/docker.sock:ro` — used by log-monitoring apps (e.g., dozzle).

---

## Template Variables

Available in `docker-compose.yml.template`:

| Variable | Description | Example |
|---|---|---|
| `{{ portal.domain }}` | Shard's FQDN | `8271dd.example.com` |
| `{{ portal.id }}` | Full shard hash-ID | `8271dd...` (long) |
| `{{ portal.short_id }}` | First 6 chars of shard ID | `8271dd` |
| `{{ portal.public_key_pem }}` | Shard's public key (PEM) | `-----BEGIN PUBLIC KEY-----...` |
| `{{ fs.app_data }}` | App-specific persistent storage | `/data/apps/my-app` |
| `{{ fs.all_app_data }}` | Parent of all app data dirs | `/data/apps` |
| `{{ fs.shared }}` | Shared dir for inter-app data | `/data/shared` |

Available in `paths[].headers` values only:

| Variable | Description | Values |
|---|---|---|
| `{{ auth.client_type }}` | Type of connecting client | `"terminal"`, `"peer"`, `"anonymous"` |
| `{{ auth.client_id }}` | Cryptographic client identifier | (opaque string) |
| `{{ auth.client_name }}` | User-assigned client name | (string) |

---

## Access Modes

Set per path prefix in `paths`. Longest prefix wins.

| Mode | Who can access | Typical use |
|---|---|---|
| `"private"` | Paired/authenticated devices only | Single-user personal apps |
| `"public"` | Anyone (no auth) | Apps with own auth, public-facing paths |
| `"peer"` | Peer shards | Inter-shard federation |

### Common patterns

**Fully private** (most common):
```json
"paths": { "": { "access": "private" } }
```

**Private + auth-proxy header** (auto-login via reverse proxy):
```json
"paths": { "": { "access": "private", "headers": { "X-Ptl-User": "admin" } } }
```
App must be configured to trust the header. See auth-proxy section below.

**Public (app manages auth)**:
```json
"paths": { "": { "access": "public" } }
```

**Mixed access** (private default, specific paths public):
```json
"paths": {
  "": { "access": "private" },
  "/share/": { "access": "public" },
  "/api/public/": { "access": "public" }
}
```
Real example: paperless-ngx exposes `/share/` publicly; docuseal exposes `/d/`, `/s/`, `/disk/`, `/packs/`, `/api/attachments`, `/submitters/` publicly.

**MQTT with mixed access** (mosquitto):
```json
"paths": {
  "": { "access": "private" },
  "/mqtt": { "access": "public" }
}
```

---

## Lifecycle

Controls auto-start/stop behavior. Configured in `lifecycle` block.

| Setting | Behavior | When to use |
|---|---|---|
| `always_on: true` | Never auto-stops | IoT, messaging, background daemons (mosquitto, node-red) |
| `idle_time_for_shutdown: N` | Stops after N seconds of no HTTP traffic | All other apps |

`always_on` and `idle_time_for_shutdown` are mutually exclusive.

### Guidelines by app type

| App type | Recommended setting |
|---|---|
| Simple web app | `idle_time_for_shutdown: 60` (default) |
| Background processing (e.g., paperless-ngx) | `idle_time_for_shutdown: 300` |
| Heavy background tasks (e.g., immich, navidrome) | `idle_time_for_shutdown: 3600` |
| Log monitoring (dozzle) | `idle_time_for_shutdown: 3600` |
| IoT/messaging services | `always_on: true` |
| Apps with slow startup | Higher idle timeout to avoid churn |

---

## `minimum_portal_size` Classes

Set only when the app requires meaningful resources. Omit for lightweight apps (defaults to `"xs"`).

| Value | When to use | Examples |
|---|---|---|
| (omit / `"xs"`) | Lightweight apps | linkding, navidrome, filebrowser |
| `"s"` | Moderate resource needs | immich, paperless-ngx |
| `"m"` | Heavy resource needs | overleaf |

---

## Common Patterns

### Auth-proxy (reverse proxy auto-login)

Configure `X-Ptl-User: admin` header in paths, then set app env vars to trust the header:

| App | Env vars |
|---|---|
| linkding | `LD_ENABLE_AUTH_PROXY=True`, `LD_AUTH_PROXY_USERNAME_HEADER=HTTP_X_PTL_USER`, `LD_SUPERUSER_NAME=admin` |
| navidrome | `ND_REVERSEPROXYUSERHEADER=X-Ptl-User`, `ND_REVERSEPROXYWHITELIST=0.0.0.0/0` |
| paperless-ngx | `PAPERLESS_AUTO_LOGIN_USERNAME=admin` |

### Shared data paths

Mount `{{ fs.shared }}/...` to give apps access to shared user files:

| Path | Convention | Used by |
|---|---|---|
| `{{ fs.shared }}/documents` | Documents | paperless-ngx |
| `{{ fs.shared }}/music` | Music files | navidrome |
| `{{ fs.shared }}/pictures` | Photos | immich, photoprism |
| `{{ fs.shared }}/media` | General media | (various) |

### Telemetry opt-outs

Always disable analytics/telemetry. Each app has its own env var — check upstream docs. Example: `DOZZLE_NO_ANALYTICS=true`.

### Base URL pattern

```
BASE_URL=https://<name>.{{ portal.domain }}
```
or `PAPERLESS_URL=https://paperless-ngx.{{ portal.domain }}` — varies by app env var name.

### Internal service references

Supporting services reference each other by `container_name` (Docker DNS on shared network):
```
DATABASE_URL=postgres://user:pass@my-app-postgres:5432/db
REDIS_URL=redis://my-app-redis:6379
```

---

## Update Flow

### `update.py` commands

| Command | Effect |
|---|---|
| `check` | Queries GitHub releases for all apps with `upstream_repo`; writes `update_info.json` |
| `skip <app>...` | Marks apps as skipped (no update) |
| `update` | Applies new version strings to all `outdated` apps' files |
| `test` | Verifies Docker images can be pulled |
| `build` | Rebuilds zip artifacts |
| `commit` | Creates branch, commits per-app, merges |

### Manual update steps

1. Update `app_version` in `app_meta.json`.
2. Update image tag in `docker-compose.yml.template` (must match `app_version`).
3. Update `.env` if it contains version refs.
4. Run `python -m build_store_data`.

### `adapt_version_string` — tag normalization

Some apps use Docker image tags that differ from GitHub release tag format. Handled in `update.py:adapt_version_string`:

| Rule | Apps |
|---|---|
| Strip `v` prefix | actual, audiobookshelf, drawio, etherpad, kavita, linkding, navidrome, paperless-ngx, stirling-pdf, grist, memos |
| Strip suffix after `-` | element |
| Append `-full` suffix | glances |

When adding a new app: check whether GitHub release tag format matches Docker image tag. If not, add app to `adapt_version_string`.

---

## Build Artifact

After any changes to `app_meta.json` or `docker-compose.yml.template`:

```
python -m build_store_data
```

This regenerates `<app-name>.zip` and updates `store_metadata.json`. The zip is the installation artifact — do not edit it manually.

---

## Checklist (new app)

- [ ] `just new-app <name>`
- [ ] Set image, container_name, volumes, env, networks in template
- [ ] Fill all fields in `app_meta.json` (version, entrypoints, paths, lifecycle, store_info)
- [ ] `upstream_repo` if on GitHub
- [ ] Icon file (SVG preferred)
- [ ] Auth-proxy env vars if using `private` + header auth
- [ ] `{{ fs.shared }}/...` mounts if app accesses shared data
- [ ] `minimum_portal_size` if resource-heavy
- [ ] `always_on: true` if must run continuously
- [ ] Disable telemetry env vars
- [ ] `python -m build_store_data`
