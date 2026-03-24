# Freeshard App Repository - Agent Guide

This document describes how to create, configure, and modify apps in the Freeshard app store. Each app lives in `apps/<app-name>/` and consists of a few key files.

## Repository Structure

```
apps/
  <app-name>/
    app_meta.json                  # App metadata and configuration
    docker-compose.yml.template    # Docker Compose template with Jinja-like variables
    icon.svg (or .png)             # App icon
    <app-name>.zip                 # Built artifact (auto-generated, do not edit)
    .env                           # Optional, for complex multi-service apps
inactive_apps/
  template/                        # Skeleton for new apps
justfile                           # `just new-app <name>` scaffolds a new app
build_store_data.py                # Builds store_metadata.json and zip files
update.py                          # Checks GitHub releases for version updates
```

## Creating a New App

1. Run `just new-app <name>` to scaffold from the template.
2. Edit `apps/<name>/app_meta.json` - fill in all `$$edit$$` placeholders.
3. Edit `apps/<name>/docker-compose.yml.template` - set the correct image and configuration.
4. Add an icon file (`icon.svg` preferred, or `icon.png`).
5. Run `python -m build_store_data` to generate the zip and update store metadata.

The app name must be lowercase, using only letters, numbers, and dashes. It becomes the subdomain: `<name>.<shard-domain>`.

## app_meta.json Reference

```jsonc
{
  "v": "1.2",                           // Format version. Use "1.2" for new apps (supports homepage/upstream_repo). "1.1" and "1.0" also exist.
  "app_version": "1.0.0",               // App version string. Must match the docker image tag used in docker-compose.yml.template.
  "name": "my-app",                     // Unique identifier. Lowercase, letters/numbers/dashes only. Must match folder name.
  "pretty_name": "My App",              // Optional. Display name with proper casing. Defaults to titlecased name.
  "icon": "icon.svg",                   // Icon filename. Must exist in the app folder.
  "homepage": "https://example.com",    // Optional (v1.2+). App's homepage URL.
  "upstream_repo": "https://github.com/org/repo",  // Optional (v1.2+). GitHub repo for automatic update checking.

  "entrypoints": [                      // Required. At least one entrypoint.
    {
      "container_name": "my-app",       // Must match a container_name in docker-compose.yml.template.
      "container_port": 8080,           // The port the container listens on internally.
      "entrypoint_port": "http"         // "http" (maps to 443) or "mqtt" (maps to 8883).
    }
  ],

  "paths": {                            // Required. Access control rules by path prefix.
    "": {                               // Default/catch-all rule (empty string = all paths). Required.
      "access": "private",              // "private" (paired devices only), "public" (anyone), or "peer" (peer shards).
      "headers": {                      // Optional. Headers forwarded to the app.
        "X-Ptl-Client-Id": "{{ auth.client_id }}",
        "X-Ptl-Client-Name": "{{ auth.client_name }}",
        "X-Ptl-Client-Type": "{{ auth.client_type }}",
        "X-Ptl-User": "admin"           // Common pattern for auth-proxy: send a static username.
      }
    },
    "/public/": {                       // More specific prefixes take priority (longest match wins).
      "access": "public",
      "headers": {
        "X-Ptl-Client-Type": "{{ auth.client_type }}"
      }
    }
  },

  "lifecycle": {                        // Optional. Controls start/stop behavior.
    "always_on": false,                 // true = never auto-stop. Cannot be used with idle_time_for_shutdown.
    "idle_time_for_shutdown": 60        // Seconds of no HTTP traffic before auto-stop. Default: 60. Use higher values for apps with background tasks.
  },

  "minimum_portal_size": "s",           // Optional. Minimum shard size required. Omit for lightweight apps (defaults to "xs").

  "store_info": {                       // Required. App store display information.
    "description_short": "One-line description of the app.",
    "description_long": [               // Optional. Array of paragraphs (strings) or a single string.
      "First paragraph.",
      "Second paragraph."
    ],
    "hint": [                           // Optional. Array of usage hints shown to the user.
      "Tip: configure X before first use."
    ],
    "is_featured": false                // Optional. Whether to highlight in the app store.
  }
}
```

### Access Control Patterns

Most apps use one of these approaches:

**Fully private** (most common for single-user apps):
```json
"paths": { "": { "access": "private" } }
```

**Private with auth-proxy headers** (for apps that support reverse proxy auth):
```json
"paths": {
  "": {
    "access": "private",
    "headers": { "X-Ptl-User": "admin" }
  }
}
```
The app must be configured to trust the proxy header (see linkding, navidrome examples).

**Public with app-managed auth** (for apps with built-in user management):
```json
"paths": { "": { "access": "public" } }
```
Used when the app handles its own authentication (e.g., immich, affine).

**Mixed access** (private by default, some paths public):
```json
"paths": {
  "": { "access": "private" },
  "/share/": { "access": "public" },
  "/api/public/": { "access": "public" }
}
```

### Header Template Variables

Available in `paths[].headers` values:
- `{{ auth.client_type }}` - "terminal", "peer", or "anonymous"
- `{{ auth.client_id }}` - Cryptographic client identifier
- `{{ auth.client_name }}` - User-assigned client name

### Lifecycle Guidelines

- Simple web apps: `idle_time_for_shutdown: 60` (default)
- Apps with background processing: `idle_time_for_shutdown: 300` to `3600`
- IoT/messaging services (mosquitto, node-red): `always_on: true`
- Apps that take a long time to start: higher idle timeout to avoid frequent restarts

## docker-compose.yml.template Reference

Templates use Jinja-like `{{ variable }}` syntax. Variables are replaced at installation time.

### Template Variables

| Variable | Description | Example Value |
|---|---|---|
| `{{ portal.domain }}` | Shard's fully qualified domain | `8271dd.example.com` |
| `{{ portal.id }}` | Full shard hash-ID | `8271dd...` |
| `{{ portal.short_id }}` | First 6 chars of shard ID | `8271dd` |
| `{{ portal.public_key_pem }}` | Shard's public key (PEM) | `-----BEGIN PUBLIC KEY-----...` |
| `{{ fs.app_data }}` | App-specific persistent storage path | `/data/apps/my-app` |
| `{{ fs.all_app_data }}` | Parent directory of all app data | `/data/apps` |
| `{{ fs.shared }}` | Shared directory for inter-app data | `/data/shared` |

### Minimal Template (simple single-container app)

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

### Template with Database (e.g., PostgreSQL + Redis)

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
        volumes:
        - "{{ fs.app_data }}/data:/app/data"
        environment:
        - DATABASE_URL=postgres://myapp:myapp@my-app-postgres:5432/myapp
        - REDIS_URL=redis://my-app-redis:6379
        - BASE_URL=https://my-app.{{ portal.domain }}
        depends_on:
        - my-app-postgres
        - my-app-redis
        networks:
        - portal
        - my-app

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
        networks:
        - my-app

    my-app-redis:
        restart: always
        image: redis:7-alpine
        container_name: my-app-redis
        networks:
        - my-app
```

### Key Rules

1. **Portal network**: Every template must declare the `portal` external network. All containers that need to be reachable (by the reverse proxy or by other apps) must join it.
2. **Container names**: Every service must have an explicit `container_name`. The main service's container_name must match the `entrypoints[].container_name` in app_meta.json.
3. **Supporting services**: Name them `<app-name>-<service>` (e.g., `paperless-redis`, `affine-postgres`).
4. **Volumes**: Use `{{ fs.app_data }}/...` for app-specific persistent data. Use `{{ fs.shared }}/...` for shared user data (documents, music, pictures, media).
5. **restart**: Always set to `always` (or `unless-stopped`). Use `restart: no` only for one-shot init/migration containers.
6. **Image tags**: Pin to a specific version matching `app_version` in app_meta.json. Do not use `latest`.
7. **Internal networking**: Supporting services (databases, caches) can reference each other by container_name since they're on the same network.
8. **Docker socket**: Can be mounted read-only if needed: `/var/run/docker.sock:/var/run/docker.sock:ro` (used by dozzle).
9. **Private networks**: For multi-service apps, only the entrypoint container should join the `portal` network. Create an additional private network (named after the app) for internal communication between all services. The entrypoint container joins both networks; supporting services join only the private network. See immich for examples.

### Common Shared Directory Paths

- `{{ fs.shared }}/documents` - Documents (used by paperless-ngx)
- `{{ fs.shared }}/music` - Music files (used by navidrome)
- `{{ fs.shared }}/pictures` - Photos (used by immich, photoprism)
- `{{ fs.shared }}/media` - General media

### Environment Variable Patterns

- **Base URL**: `BASE_URL=https://<name>.{{ portal.domain }}`
- **Disable telemetry**: Most apps have a telemetry opt-out env var - always disable it.
- **Auto-login / auth-proxy**: When using `private` access with header-based auth, configure the app to trust the proxy and auto-login. Examples:
  - linkding: `LD_ENABLE_AUTH_PROXY=True`, `LD_AUTH_PROXY_USERNAME_HEADER=HTTP_X_PTL_USER`
  - navidrome: `ND_REVERSEPROXYUSERHEADER=X-Ptl-User`, `ND_REVERSEPROXYWHITELIST=0.0.0.0/0`
  - paperless-ngx: `PAPERLESS_AUTO_LOGIN_USERNAME=admin`

## Version Updates

The `update.py` script automates version updates for apps with `upstream_repo` set:

1. `python update.py check` - Checks GitHub releases for all apps.
2. `python update.py skip <app1> <app2>` - Skip specific apps from updating.
3. `python update.py update` - Updates version strings in all config files.
4. `python update.py test` - Verifies Docker images can be pulled.
5. `python update.py build` - Builds updated zip files.
6. `python update.py commit` - Creates a branch, commits per-app, and merges.

When updating an app version manually:
- Update `app_version` in `app_meta.json`.
- Update the image tag in `docker-compose.yml.template`.
- Update any `.env` file if it contains versions.
- Run `python -m build_store_data` to rebuild the zip.

### Version String Conventions

Some apps strip or add prefixes to GitHub release tags (handled in `update.py:adapt_version_string`):
- Apps that strip the `v` prefix: actual, audiobookshelf, drawio, etherpad, kavita, linkding, navidrome, paperless-ngx, stirling-pdf, grist, memos
- element: strips suffix after `-`
- glances: appends `-full`

When adding a new app, check whether the Docker image tag matches the GitHub release tag format and add an entry to `adapt_version_string` if needed.

## Checklist for Adding a New App

- [ ] `just new-app <name>`
- [ ] Find the app's Docker image (Docker Hub, ghcr.io, etc.) and determine the correct image name and tag format
- [ ] Edit `docker-compose.yml.template`: set image, container_name, volumes, environment, networks
- [ ] Edit `app_meta.json`: set app_version, name, pretty_name, icon, entrypoints (correct port), paths, lifecycle, store_info
- [ ] Set `upstream_repo` if the app is on GitHub (enables auto-updates)
- [ ] Add an icon file (SVG preferred)
- [ ] If the app needs auth-proxy support, configure the appropriate environment variables
- [ ] If the app needs shared data (media, documents), mount `{{ fs.shared }}/...`
- [ ] If the app is resource-heavy, set `minimum_portal_size: "s"`
- [ ] If the app needs to run continuously (IoT, messaging), set `always_on: true`
- [ ] Disable telemetry/analytics via environment variables if the app supports it
- [ ] Run `python -m build_store_data` to generate the zip

## Checklist for Modifying an Existing App

- [ ] Read the current `app_meta.json` and `docker-compose.yml.template`
- [ ] Make changes
- [ ] Ensure `app_version` in app_meta.json matches the image tag in docker-compose.yml.template
- [ ] Run `python -m build_store_data` to regenerate the zip
