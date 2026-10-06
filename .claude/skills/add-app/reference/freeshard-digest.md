# Freeshard App Integration Digest

Compact reference for integrating a new app into the Freeshard app store.
Generated 2026-10-02 from docs.freeshard.net developer docs.

## Mental model

- A **shard** = one owner's dedicated VM + disk (single-user isolation). No multi-tenant
  anything; privacy comes from infrastructure isolation, not app-level ACLs.
- An **app** = one or more Docker images run as containers on the shard, plus metadata files.
  Exactly one container must serve **plain HTTP (not HTTPS!)** on a port — the shard terminates
  TLS for you.
- Apps behave like phone apps: installed in large numbers, started on demand, stopped when idle.
- Because each shard serves one person, do NOT make the app ask users to register/log in. Let
  Freeshard's auth-proxy handle identity (see Routing & AC).
- Sharing between users uses peering / sharing links, not multi-user accounts.

## Three files per app (the deliverable)

An app = a folder in `FreeshardBase/app-repository` containing exactly:

1. `app_meta.json` — run instructions + app-store metadata
2. `docker-compose.yml.template` — compose file with template variables
3. the icon file (PNG/JPEG/SVG), referenced by `icon` in meta

The actual Docker images live on a registry (e.g. Docker Hub); the repo holds only metadata.
On install the shard fetches the template, substitutes variables, and runs it.

## app_meta.json

Schema v1.2: `https://storageaccountportab0da.blob.core.windows.net/json-schema/0-30-2/schema_app_meta_1.2.json`

### Fields

| Field | Type | Req | Notes |
|---|---|---|---|
| `v` | string | yes | Format version, `"1.2"` |
| `app_version` | string | yes | App version, used for update detection |
| `name` | string | yes | Unique id used in URLs; lowercase letters, numbers, dashes only |
| `pretty_name` | string | yes | Display name (spaces/capitals ok) |
| `icon` | string | yes | Icon filename (png/jpeg/svg) present in the folder |
| `homepage` | string | no | App's info website URL |
| `upstream_repo` | string | no | GitHub repo URL, used by update checks |
| `entrypoints` | array | yes | Port exposure, see below |
| `paths` | object | yes | Access control by path prefix, see below |
| `lifecycle` | object | yes* | Start/stop behavior, see below (defaults exist) |
| `minimum_portal_size` | string | no | enum `xs` `s` `m` `l` `xl`, default `xs`; set higher for heavy apps |
| `store_info` | object | no | App-store display metadata, see below |

**entrypoints[]** (required object fields):
- `container_name` (string) — must match a service/container_name in the compose file
- `container_port` (integer) — internal HTTP port the container serves
- `entrypoint_port` (enum) — `"http"` (public 443) or `"mqtt"` (public 8883)

**paths** — object keyed by URL path prefix; each value:
- `access` (enum, required): `"public"` | `"private"` | `"peer"`
- `headers` (object of string→string, optional) — extra headers to inject for that path
- Must include the default empty-string key `""`. Longest prefix wins (longest→shortest match).

**lifecycle**:
- `always_on` (bool, default `false`) — if `true`, app never auto-stops and
  `idle_time_for_shutdown` is forbidden
- `idle_time_for_shutdown` (int seconds, default `60`) — idle time before stop; incompatible
  with `always_on: true`

**store_info** (all optional, but see Submission for rules):
- `description_short` (string) — 1–2 sentences, fits the app card
- `description_long` (string or array of strings → paragraphs)
- `hint` (string or array of strings → bullet points)
- `is_featured` (bool) — DO NOT set in submissions (reserved for Freeshard)

### Example

```json
{
  "v": "1.2",
  "app_version": "0.1.1",
  "name": "my-app",
  "pretty_name": "My App",
  "icon": "icon.png",
  "homepage": "https://myapp.com",
  "upstream_repo": "https://github.com/namespace/myapp",
  "entrypoints": [
    { "container_name": "my-app", "container_port": 8080, "entrypoint_port": "http" }
  ],
  "paths": { "": { "access": "private" } },
  "lifecycle": { "always_on": false, "idle_time_for_shutdown": 3600 },
  "minimum_portal_size": "s",
  "store_info": {
    "description_short": "This is a very good app.",
    "description_long": ["This app is so good, you won't believe it.", "It is the best app ever."],
    "hint": "Although this app is very good, you still have to create an account to use it.",
    "is_featured": true
  }
}
```

## docker-compose.yml.template

Standard compose file; the shard substitutes Jinja2-style `{{ variable }}` placeholders at
install time. Conventions:

- `version: '3.5'`.
- Declare the external network `portal` and attach every service to it:
  ```yaml
  networks:
    portal:
      external: true
  ```
- Each service needs an explicit `container_name`. The web service's `container_name` +
  `container_port` must match an `entrypoints[]` entry. Convention for extra containers:
  `my-app-<name>` (e.g. `my-app-redis`).
- The web service serves plain HTTP; no TLS, no cert handling in the app.
- App is reached at `https://<name>.<shard-domain>`.

### Template variables

Portal:
- `portal.domain` — shard FQDN (e.g. `8271dd.<domain>`)
- `portal.id` — full shard hash id
- `portal.short_id` — first six chars of the id
- `portal.public_key_pem` — shard public key (PEM)

Filesystem (only these may be mounted):
- `fs.app_data` — this app's private dir (starts empty, app owns it)
- `fs.all_app_data` — parent of all apps' data dirs
- `fs.shared` — cross-app shared dir (subdirs like `documents`, `media`, `music`)
- `fs.installation_dir` — installation files location

### Volumes / env

- Mount format: `"{{ fs.app_data }}/data:/data"`, `"{{ fs.shared }}/documents:/documents"`.
- Docker socket, if needed, must be read-only: `"/var/run/docker.sock:/var/run/docker.sock:ro"`.
- Inject env with template vars, e.g. `BASE_URL=https://my-app.{{ portal.domain }}`,
  `TITLE=My app on {{ portal.short_id }}`, `REDIS_HOST=my-app-redis`.

### Example (multi-container)

```yaml
version: '3.5'
networks:
  portal:
    external: true
services:
  my-app:
    image: my-app:v4
    container_name: my-app
    depends_on:
      - my-app-redis
    volumes:
      - "{{ fs.app_data }}/data:/data"
      - "{{ fs.shared }}/shared_data:/shared_data"
    networks:
      - portal
    environment:
      - REDIS_HOST=my-app-redis
      - BASE_URL=https://my-app.{{ portal.domain }}
      - TITLE=My app on {{ portal.short_id }}
  my-app-redis:
    image: redis:6.2
    container_name: my-app-redis
    volumes:
      - "{{ fs.app_data }}/redis_data:/redis_data"
    networks:
      - portal
```

## Routing & access control

- Shard has a unique domain `xyz123.<domain>`; apps live at `<name>.xyz123.<domain>`.
- Shard core reverse-proxies HTTP to the container port from `entrypoints`. TLS is terminated
  by the shard (one cert covers all app subdomains). App exposes plain HTTP only.
- `paths` map decides AC per URL prefix (longest prefix first; `""` is the required default):
  - `public` — anyone, no auth
  - `private` — only the owner's paired devices
  - `peer` — peered shards
- On every forwarded request the shard injects identity headers the app can trust:
  - Client: `X-Ptl-Client-Id`, `X-Ptl-Client-Name`, `X-Ptl-Client-Type`
  - (peer requests carry the peer's id/name analogously)
- **How the owner authenticates:** a paired device holds a JWT (device id + secret) as a cookie;
  the shard validates it and forwards the request with the `X-Ptl-Client-*` headers set. The app
  does not implement login.
- Two AC strategies:
  1. **Path-based** — set public/private/peer per path in `app_meta.json`; app needs no auth code.
  2. **App-specific** — set paths to `public` and let the app authorize itself using the injected
     `X-Ptl-Client-*` headers (useful when adapting an app with its own user model).

## Lifecycle

- Install: containers created but not started (`docker-compose up --no-start`).
- Start: reverse proxy sees incoming HTTP, signals shard core to launch; a splash screen shows
  during startup.
- Stop: after `idle_time_for_shutdown` seconds without HTTP, shard core runs
  `docker-compose stop`; containers persist and can restart.
- `always_on: true` keeps it running permanently.
- No documented uninstall/update hooks or custom scripts; app must self-migrate data across
  version changes.

## Persisting data

- `fs.app_data` — app-private dir, starts empty, survives stop/restart/update. App owns layout
  and is responsible for its own data migrations across versions.
- `fs.shared` — one shared dir per shard for cross-app exchange and common user resources
  (documents, media, music). Mount the subdirs you need.
- All mounted dirs persist across restarts.

## Internal services

- **Shard core** REST API at `http://shard_core` (reachable on the `portal` network). Manages
  identities, terminals, peers, apps. E.g. `GET http://shard_core/protected/apps` lists installed
  apps. WARNING: these APIs are unauthenticated from inside the shard — an app can read/modify/
  break critical shard state. Use with care.
- **Peering**: get the peer list from shard core, then send HTTP to peers *through* shard core
  (not directly); shard core signs/authenticates and forwards. Restrict peer-only paths via
  `paths` with `access: "peer"`; incoming peer requests carry peer id/name headers.
- **Events** (event broker, subscribe/publish on app-namespaced topics): NOT yet implemented.
- **Inter-app APIs**: NOT yet implemented.

## Submission

- Repo: `FreeshardBase/app-repository` on GitHub.
- Add one folder for your app containing `app_meta.json`, `docker-compose.yml.template`, and the
  icon. Open a PR; branch naming convention `app/<your-app>`.
- You may NOT modify any app other than your own. Updates = another PR touching only your files.
- `store_info`: `description_short` required (1–2 sentences); `description_long` and `hint`
  optional; do NOT set `is_featured`.
- Test before submitting by installing as a **custom app**: zip the three files (zip filename must
  exactly equal the `name` from `app_meta.json`), then Apps page → "Tools for app developers" →
  "Install Custom App" → upload. The zip can be shared with others to install directly, no store
  submission needed.

### Level-2 (existing-app) checklist

To package a third-party/existing app it must: be containerized; depend only on Freeshard
internal services; need no manual setup after startup; have modest resource demands. Then adapt
its compose into the template, write `app_meta.json`, test as custom app, and improve UX by
disabling its built-in user management in favor of proxy auth + path/app-specific AC.

## Revenue share

Each user subscription includes a flat app fee (e.g. ~3.00€/month) split monthly across their
installed apps proportional to usage time. Users can "boost" favorites to shift their share.
Developers earn per install for as long as the app stays installed, across all shards; earnings
accumulate for monthly withdrawal.
