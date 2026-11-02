# Freeshard App Integration Digest

Compact reference for integrating a new app into the Freeshard app store.
Generated 2026-11-02 from docs.freeshard.net developer docs + repo `agents.md`.

## Mental model

- A **shard** = one owner's dedicated VM + disk (single-user isolation). No multi-tenant
  anything; privacy comes from infrastructure isolation, not app-level ACLs. Freeshard calls
  people who use it "owners", not "users".
- An **app** = one or more Docker images run as containers on the shard, plus metadata files.
  Exactly one container must serve **plain HTTP (not HTTPS!)** on a port — the shard terminates
  TLS for you.
- Apps behave like phone apps: installed in large numbers, started on demand, stopped when idle.
  Because apps don't all run at once, owners can install as many as they like without
  overloading the shard.
- Because each shard serves one owner, do NOT make the app ask users to register/log in. Let
  Freeshard's auth-proxy / injected identity headers handle identity (see Routing & AC).
- Sharing between owners uses peering or sharing links, not multi-user accounts; shared data
  stays on the sharer's shard and under their control.
- Legacy naming: the project was formerly called "Portal" — this is why template variables and
  headers use a `portal.` / `X-Ptl-` prefix.

## Three files per app (the deliverable)

An app = a folder in `FreeshardBase/app-repository` (`apps/<app-name>/`) containing:

1. `app_meta.json` — run instructions + app-store metadata
2. `docker-compose.yml.template` — compose file with template variables
3. the icon file (PNG/JPEG/SVG), referenced by `icon` in meta
4. optionally `.env` (complex multi-service apps) and `update_check.py` (see repo tooling below)

The actual Docker images live on a registry (e.g. Docker Hub, ghcr.io); the repo holds only
metadata. On install the shard fetches the template, substitutes variables, and runs it.
Repo tooling: `just new-app <name>` scaffolds the folder from `inactive_apps/template/`; after
editing, `python -m build_store_data` generates the zip artifact and store metadata.

## app_meta.json

Schema v1.2: `https://storageaccountportab0da.blob.core.windows.net/json-schema/0-30-2/schema_app_meta_1.2.json`
(fetched and verified directly — see Fields below; confirmed no server-side change since 1.2).

### Fields

| Field | Type | Req | Notes |
|---|---|---|---|
| `v` | string | yes | Format version, `"1.2"` for new apps. `"1.1"` and `"1.0"` also exist/validate. |
| `app_version` | string | yes | App version; should match the image tag used in the compose template; used for update detection |
| `name` | string | yes | Unique id used in URLs; lowercase letters, numbers, dashes only; must match the folder name |
| `pretty_name` | string | yes | Display name (spaces/capitals ok); added in format v1.1 |
| `icon` | string | yes | Icon filename (png/jpeg/svg) present in the folder |
| `homepage` | string | no | App's info website URL; added in format v1.2 |
| `upstream_repo` | string | no | GitHub repo URL, used by update checks; added in format v1.2. **Only GitHub repos that use GitHub's "Release" feature work** — repos without tagged releases won't get automatic update detection |
| `entrypoints` | array | yes | Port exposure, see below |
| `paths` | object | yes | Access control by path prefix, see below |
| `lifecycle` | object | no | Start/stop behavior, see below; default `{"always_on": false, "idle_time_for_shutdown": 60}` |
| `minimum_portal_size` | string | no | enum `xs` `s` `m` `l` `xl`, default `xs`; set higher for heavy apps |
| `store_info` | object | no | App-store display metadata, see below |

No `minimum_freeshard_version` (or similar shard-version-gate) field exists in the current
schema or docs — checked both the live JSON schema and the `app_meta_json` docs page directly;
neither mentions it. If a prior version of this digest described such a field, that content did
not come from docs.freeshard.net and should be treated as unverified/stale.

**entrypoints[]** (required object fields):
- `container_name` (string) — must match a service/container_name in the compose file
- `container_port` (integer) — internal HTTP port the container serves
- `entrypoint_port` (enum) — `"http"` (public 443) or `"mqtt"` (public 8883)

**paths** — object keyed by URL path prefix; each value:
- `access` (enum, required): `"public"` | `"private"` | `"peer"`
- `headers` (object of string→string, optional) — extra headers to forward to the app for that
  path. **Headers are opt-in, not automatic**: the shard only sets a header on a request if you
  declare it here. Values use Jinja-like template vars: `{{ auth.client_type }}` (`"terminal"`,
  `"peer"`, or `"anonymous"`), `{{ auth.client_id }}`, `{{ auth.client_name }}`, plus the
  `portal.*` vars. Convention is to name the headers `X-Ptl-Client-Id` / `X-Ptl-Client-Name` /
  `X-Ptl-Client-Type` (or an app-specific one like `X-Ptl-User`), but the header name is yours to
  choose.
- Must include the default empty-string key `""`. Longest prefix wins (longest→shortest match).
- Access control applies only to `http` entrypoints — `mqtt` entrypoints are public by default
  and not gated by `paths`.

**lifecycle**:
- `always_on` (bool, default `false`) — if `true`, app never auto-stops and
  `idle_time_for_shutdown` must not be provided
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
- Declare the external network `portal` and attach every service that must be reachable (by the
  reverse proxy, or by other apps) to it:
  ```yaml
  networks:
    portal:
      external: true
  ```
- Each service needs an explicit `container_name` matching the service name. The web service's
  `container_name` + `container_port` must match an `entrypoints[]` entry.
- Supporting containers: name them `<app-name>-<service>` (e.g. `my-app-redis`,
  `paperless-redis`, `affine-postgres`).
- For multi-service apps, only the entrypoint container should join `portal`; create an
  additional private network named after the app for internal service-to-service traffic. The
  entrypoint container joins both networks; supporting services join only the private one (see
  `apps/immich` for a worked example).
- `restart: always` (or `unless-stopped`) on every long-running service; `restart: "no"` only for
  one-shot init/migration containers.
- Pin image tags to a specific version matching `app_version` — never `latest`. Release new
  metadata + a new template with each app update.
- The web service serves plain HTTP; no TLS, no cert handling in the app.
- App is reached at `https://<name>.<shard-domain>`; use `{{ portal.domain }}` for URLs since the
  domain is only known at install time.

### Template variables

Portal:
- `portal.domain` — shard FQDN (e.g. `8271dd.<domain>`)
- `portal.id` — full shard hash id
- `portal.short_id` — first six chars of the id
- `portal.public_key_pem` — shard public key (PEM)

Filesystem (only these may be mounted):
- `fs.app_data` — this app's private dir (starts empty, app owns it)
- `fs.all_app_data` — parent of all apps' data dirs (mount only with good reason)
- `fs.shared` — cross-app shared dir (subdirs: `documents`, `media`, `music`, `pictures`, ...)
- `fs.installation_dir` — installation files location

### Volumes / env

- Mount format: `"{{ fs.app_data }}/data:/data"`, `"{{ fs.shared }}/documents:/documents"`.
- Docker socket, if needed, must be read-only: `"/var/run/docker.sock:/var/run/docker.sock:ro"`
  (used by e.g. dozzle to monitor other apps).
- Inject env with template vars, e.g. `BASE_URL=https://my-app.{{ portal.domain }}`,
  `TITLE=My app on {{ portal.short_id }}`, `REDIS_HOST=my-app-redis`.
- Disable telemetry/analytics via env var whenever the upstream app offers one.
- Auth-proxy / auto-login patterns, for apps with their own user model that should trust the
  shard's identity headers instead of asking owners to log in:
  - linkding: `LD_ENABLE_AUTH_PROXY=True`, `LD_AUTH_PROXY_USERNAME_HEADER=HTTP_X_PTL_USER`
  - navidrome: `ND_REVERSEPROXYUSERHEADER=X-Ptl-User`, `ND_REVERSEPROXYWHITELIST=0.0.0.0/0`
  - paperless-ngx: `PAPERLESS_AUTO_LOGIN_USERNAME=admin`

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
    restart: always
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
    restart: always
    volumes:
      - "{{ fs.app_data }}/redis_data:/redis_data"
    networks:
      - portal
```

## Routing & access control

- Shard has a unique domain `xyz123.<domain>`; apps live at `<name>.xyz123.<domain>`.
- Shard core reverse-proxies HTTP to the container port from `entrypoints`. TLS is terminated
  by the shard (one cert covers all app subdomains). App exposes plain HTTP only. MQTT
  connections can also be forwarded this way, but MQTT is not protected by access control.
- `paths` map decides AC per URL prefix (longest prefix first; `""` is the required default),
  and applies only to `http` entrypoints:
  - `public` — anyone, no auth
  - `private` — only the owner's paired devices
  - `peer` — peered shards
- The shard authenticates the request source, then forwards *allowed* requests with whatever
  headers are declared for that path (see `paths[].headers` above) — headers are not injected
  automatically on undeclared paths.
- **How the owner authenticates:** a paired device holds a JWT (device id + secret) as a browser
  cookie; the shard validates it and, if configured, forwards the request with identity headers.
  The app does not implement login itself.
- Two AC strategies:
  1. **Path-based** — set public/private/peer per path in `app_meta.json`; app needs no auth code.
  2. **App-specific** — set paths to `public`, declare the identity headers, and let the app
     authorize itself using them (useful when adapting an app with its own user model). An
     unauthenticated request gets `client_type = "anonymous"` with empty id/name.

## Lifecycle

- Install: image pulled, containers created but not started (`docker-compose up --no-start`).
- Start: reverse proxy sees incoming HTTP and tells shard core to launch the app if not running;
  a splash screen (refreshing automatically) shows during startup — app developers don't
  implement this themselves.
- Stop: after `idle_time_for_shutdown` seconds without HTTP, shard core runs roughly
  `docker-compose stop`; containers persist (not removed) and can restart.
- `always_on: true` keeps it running permanently; cannot be combined with
  `idle_time_for_shutdown`.
- No documented uninstall/update hooks or custom scripts; app must self-migrate data across
  version changes (see Persisting data).

## Persisting data

- `fs.app_data` — app-private dir, starts empty, survives stop/restart/update. App owns layout
  and is responsible for its own data migrations across versions (detect old-version layout on
  startup and migrate).
- `fs.shared` — one shared dir per shard for cross-app exchange and common owner resources;
  common subdirs: `documents` (paperless-ngx), `music` (navidrome), `pictures` (immich,
  photoprism), `media` (general). Mount the subdirs you need.
- All mounted dirs persist across restarts. No backup behavior is documented on the dev docs
  (handled by Freeshard infrastructure, not app-visible).

## Internal services

- **Shard core** REST API at `http://shard_core` (reachable on the `portal` network). Manages
  identities, terminals, peers, apps. E.g. `GET http://shard_core/protected/apps` lists installed
  apps. Full API reference: `https://ptl.gitlab.io/portal_core/`. WARNING: these APIs are
  currently **unauthenticated/unchecked from inside the shard** — an app could read, modify, or
  break critical shard state. The docs say this will be "locked down in the future" with no
  committed timeline — use with care.
- **Inter-app APIs** (apps calling other apps directly on the same shard): NOT yet implemented;
  docs flag the eventual design as subject to change.
- **Peering** and **Events**: see dedicated sections below.

## Peering

- **Status: currently disabled** — the docs state peering is turned off because no app in the
  store uses it yet, and ask developers who want to build on it to contact the Freeshard team
  first. Treat anything below as the intended design, not something installable today.
- Purpose: let an app talk to another instance of itself running on a peer shard, end-to-end
  encrypted and authenticated; both shards must add each other as peers first.
- Division of responsibility: shard core manages the peer list (id/name), signs outgoing
  requests, and verifies incoming signatures before handing requests to the app. The app
  developer queries the peer list, defines send/receive logic and its own ACLs, and wires
  `app_meta.json`. Every outgoing call needs a matching incoming endpoint on the peer (symmetric
  routes).
- List peers: `GET http://shard_core/protected/peers`.
- Call a peer (never directly — the peer couldn't authenticate a direct call): send to
  `http://shard_core/internal/call_peer/<peer_id>/<path>`; shard core adds the auth header and
  forwards it over the peer's public URL (`my-app.<peer_id>.<domain>/<path>`), where the peer's
  proxy + core verify the signature and apply that peer's own `paths` access control before
  routing to the app.
- Restrict peer-only endpoints with `access: "peer"` in `paths`; incoming peer requests carry the
  peer's id/name via whatever headers you declare.

## Events

- **Status: not yet implemented.** Docs explicitly say "Events are not yet implemented" and that
  the eventual design may differ from what's described.
- Planned design: each shard has a built-in event broker; apps can subscribe to any topic and
  publish to topics within their own app-specific namespace; the broker also publishes relevant
  shard-wide system events.

## Submission

- Repo: `FreeshardBase/app-repository` on GitHub; each app is a folder (`apps/<name>/`).
- Add one folder for your app containing `app_meta.json`, `docker-compose.yml.template`, and the
  icon. Open a PR; branch naming convention `app/<your-app>`.
- You may NOT modify any app other than your own. Updates = another PR touching only your files.
- `store_info`: `description_short` required (1–2 sentences); `description_long` and `hint`
  optional; do NOT set `is_featured` (Freeshard sets that).
- The docs say only to submit once the app is "ready and tested" — test it as a **custom app**
  first (see below); zip filename must exactly equal the `name` from `app_meta.json`.
- This repo's own tooling, beyond the docs: `blocked_apps/` records researched-but-rejected apps
  (non-FOSS license, no Docker image, paid tier, etc. — schema in `blocked_apps/README.md`);
  `update.py` + the `/update-apps` skill handle the recurring version-bump pass, separate from
  first-time submission.

## Existing-app integration levels

The docs now define four explicit levels (new framework; the previous digest only described the
level-2 checklist):

- **Level 1 — Blocked**: can't run on Freeshard at all (no Docker image, needs external
  services or specific hardware, etc.).
- **Level 2 — Usable with caveats**: containerized backend + web UI, depends only on Freeshard's
  internal services, needs no manual setup after first start (no migration/user-creation step),
  modest CPU/memory needs. Most self-hosted apps land at level 1 or 2.
- **Level 3 — Generally adapted**: level 2 plus configurable for single-user use (disable its own
  user management or use proxy auth) and a clean separation of public vs. protected HTTP paths so
  path-based AC works. Some apps reach this level.
- **Level 4 — Specifically adapted**: level 3 plus using Freeshard's peering feature for
  multi-owner scenarios. Docs state no app currently reaches level 4 (consistent with peering
  being disabled, see above).

Checklist to package an existing app (level 2+):
1. Confirm it meets level-2 requirements; adapt only if the changes are quick.
2. Write `docker-compose.yml.template` from the upstream compose file, checking volume mounts and
   env vars against Freeshard's constraints.
3. Write `app_meta.json` from the documented example, validated against the schema.
4. Test on a real (or free trial) shard by installing as a custom app.
5. Further adapt for level 3: disable sign-up/login or wire proxy auth so the shard's header
   becomes the username; add path-based or app-specific AC for any public/peer-facing endpoints.

No formal catalog of existing apps is published on the docs site itself; the installed catalog
lives in this repo's `apps/` directory.

## Custom apps

- Install a personal app without submitting to the store, or test before submitting.
- Zip exactly `app_meta.json`, `docker-compose.yml.template`, and (optional) an icon file; the
  zip's filename must exactly equal `name` from `app_meta.json`.
- UI: Apps page → "Tools for app developers" → "Install Custom App" → upload the zip. It then
  installs like any store app.
- The zip holds only metadata/template, not the app itself, so it's small enough to email; anyone
  can install and test it the same way, with no store submission needed.

## Revenue share

- Each owner's subscription includes a flat monthly app fee (example figure: 3.00€); owners pay
  nothing extra per install.
- Split mechanics: the shard tracks installed-time share per app over the month and weights the
  flat fee accordingly (e.g. 50/25/25 split by installed-time share in the docs' example).
- **Boosting / manual weight adjustment is explicitly called out as not yet implemented** on the
  docs page, and may change when it ships — don't build around exact boost semantics yet.
- Developer payout: each app's share across all shards accumulates to the developer's Freeshard
  account; withdraw any time or set up automatic bank transfers.
- Incentive shape: ongoing maintenance pays off since earnings depend on staying installed, not
  just being installed once; broad/versatile apps earn more when an owner has fewer competing
  apps installed.

## Single-user isolation concept

- Each shard = one owner's own VM + disk; ownership is enforced by infrastructure, not just
  application-level ACLs — unlike multi-tenant SaaS where one database/app instance serves many
  users and the provider can see everyone's data.
- Design implication: assume exactly one owner per app instance. Multi-user-by-default
  self-hosted apps need adapting — owners can't let others sign up or run apps on their shard.
- Sharing must be a deliberate, per-item feature (unguessable/time-limited links, or
  app-specific peer-to-peer sharing) rather than ambient multi-user accounts; shared data stays
  on the owner's shard and under their control.
- Upside: privacy by design (data lives in one place, one owner, smaller breach blast radius);
  downside: features that depend on pooling data across many people need a decentralized
  alternative (e.g. peering) instead of a shared backend.

## Devices concept

- A shard is a cloud computer; owners reach it only through other devices (laptop, phone), so
  those devices need pairing to prove they belong to the owner.
- Pairing is one-time: an already-paired device generates a one-time code that a new device uses
  to pair; the very first code is issued at sign-up. Once paired, a device has full access to the
  shard's web UI and every app. Unpaired visitors see only the shard's public view and whatever
  data apps explicitly publish.
- After pairing, the device gets a JWT (device id + secret) stored as a browser cookie —
  technically the *browser* is what's paired, not the device as hardware. Transport security is
  plain HTTPS: the shard authenticates via its certificate, the browser via its JWT.
- Only paired browsers get `private`-level access; everyone else is limited to `public` paths and
  published app data.
- Conceptual inversion vs. typical cloud products: the shard (not the device) is the primary
  platform; devices are secondary, interchangeable access points once Freeshard is
  feature-complete.
