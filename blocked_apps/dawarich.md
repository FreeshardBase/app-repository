# Dawarich

**Blocked:** 2026-09-28
**Exit code:** k
**Reason:** Needs `{{ secret('...') }}` compose-template secrets, which are merged into core but not yet released to shards — and an app cannot declare the core version it requires.

| Field | Value |
|---|---|
| Homepage | https://dawarich.app |
| Upstream repo | https://github.com/Freika/dawarich |
| License | AGPL-3.0 (foss) |
| Image | `freikin/dawarich:1.15.2` (multi-arch manifest verified, amd64 + arm64) |
| Description | Self-hosted replacement for Google Timeline: track, map and analyse your own location history. |
| Paid | false (AGPL, no licence key; maintainer monetises a hosted Cloud offering) |
| Auth-proxy | not supported (email+password and OIDC only — no header-trust variable exists) |

## Reason for block

This is **not** a rejection on the app's merits. Dawarich passes every inclusion criterion:
FOSS licence, official image referenced by upstream's own compose, actively maintained
(1.15.2 released 2026-09-22), no GPU or privileged mode, and a seeded admin account so
first-run needs no shell access. It is blocked purely on a platform dependency.

Dawarich runs Rails in production mode, which **requires** `SECRET_KEY_BASE`. Upstream
defaults it to the literal `CHANGE_ME`. The value signs session cookies, so it must be
unguessable, stable across restarts, and different per shard. None of the compose template
variables satisfies that: `portal.public_key_pem` and `portal.id` are public by definition,
so deriving from them means anyone who can read the shard's public key can forge a login
cookie; a hardcoded constant ships the same signing key to every installation.

The mechanism that does satisfy it is `{{ secret('secret_key_base') }}` from
FreeshardBase/freeshard#138 (PR #173), merged 2026-09-28. It mints a 32-char app-scoped
secret on first render and persists it per shard.

The remaining problem is rollout. The feature is in core `main` but not on shards, and an
app in the store **cannot declare which core version it needs** — there is no
`minimum_core_version`, and the store catalogue carries only `app_version` and
`minimum_portal_size`. Publishing Dawarich now would render an empty `SECRET_KEY_BASE` on
every shard still on an older core, and Rails would refuse to boot. Tracked as
FreeshardBase/freeshard#242.

## What unblocks it

1. A core release containing #138's `{{ secret(...) }}` support, rolled out to shards; **and**
2. FreeshardBase/freeshard#242, so the app can state its requirement instead of relying on
   every shard having upgraded.

With (1) alone, publishing is a judgement call about how many shards lag. (2) is what makes
it safe.

Then delete this file and re-run `/add-app dawarich`, reusing the drafts below.

## Open decisions (never settled)

The add-app run stopped at the phase-3 ambiguity gate, so these were drafted with
recommended defaults but **not approved**:

- **API exposure.** Phone trackers authenticate with a Dawarich API key, not shard pairing,
  so something must be public or live tracking cannot work. The draft exposes only the three
  ingest namespaces (`owntracks`, `overland`, `traccar`), confirmed from upstream
  `config/routes.rb` as the only tracker ingest routes, keeping the whole read/write data API
  private. The wider alternative is all of `/api/`.
- **Lifecycle.** The draft uses `always_on: true`, because a phone POSTs continuously and a
  cold start (up to five minutes on first boot) would time those POSTs out and leave gaps in
  the history. The cost is roughly 1.2–1.5 GB resident permanently on a 4 GB shard.
- **`v: "1.2"`.** agents.md still tells new apps to use 1.2, but core is at `CURRENT_VERSION
  = "1.3"`. 1.2 is migrated forward on read, and the draft's `always_on` lifecycle survives
  that migration untouched — but see FreeshardBase/calendar#152 for the same mismatch biting
  another app.

## Research notes

**Auth-proxy:** none. `docker/.env.example` at 1.15.2 documents every auth knob — the OIDC
set, `ALLOW_EMAIL_PASSWORD_REGISTRATION` (default `false` self-hosted),
`ALLOW_EMAIL_PASSWORD_LOGIN` (default `true`) — and there is no header-trust variable, so the
`X-Ptl-User` pattern has nothing to bind to. The user meets Dawarich's own login screen
behind shard pairing.

**First-run:** a seeded account, not a shell step. `docker/web-entrypoint.sh` runs
`rails db:seed` on every start; `db/seeds.rb` creates `demo@dawarich.app` / `safepassword`
as admin when the user table is empty. Publicly documented in the README. No `docker exec`
needed, so this is not exit `j` — but the credentials must be surfaced in `store_info.hint`
and the app must never be `access: public`.

**Topology:** four containers. `dawarich` (Puma web, port 3000) is the only one on `portal`;
`dawarich-sidekiq` (same image, `sidekiq-entrypoint.sh`), `dawarich-db`
(`postgis/postgis:17-3.5-alpine`, needs `shm_size: 1G`) and `dawarich-redis`
(`redis:7.4-alpine`) sit on the app-private network. Sidekiq is **not** optional — without it
imports, reverse geocoding and stats do nothing. Upstream compose:
`https://raw.githubusercontent.com/Freika/dawarich/1.15.2/docker/docker-compose.yml`.

**Root/permissions:** the Dockerfile has no `USER`, so the image already runs as root and can
write root-owned bind mounts — `user: "0:0"` is unnecessary. Upstream explicitly warns
against setting `user:` (use `PUID`/`PGID`), so both are left unset deliberately.

**Updates:** releases are plain (not prerelease — `[.[].prerelease] | all` is `false`), tags
carry no `v` prefix, so `latest_github_release("Freika/dawarich")` works and no
`adapt_version_string` entry is needed.

**Telemetry:** nothing to opt out of. `PROMETHEUS_EXPORTER_ENABLED=false` is a local exporter.
Geocoding providers are unset by default, so no location data leaves the shard. The one
outbound vendor call is the "What's New" changelog widget, per-user opt-in; leave
`CHIBICHANGE_*` unset. Map tiles are fetched by the browser from an external tile server —
client-side and unavoidable for a map app.

**Shared volumes:** none for v1. Dawarich's data is its own, so `fs.app_data` throughout. The
watched-imports directory (`/var/app/tmp/imports/watched`) auto-ingests dropped files and
would be a natural `fs.shared` mount, but no shared-path convention exists for location
exports and inventing one belongs in a separate change.

**Rejected image:** `ghcr.io/freika/dawarich` — `docker manifest inspect` returns `denied`,
the package is not published there.

**Security note:** upstream mounts the Postgres data directory a second time into the web
container (`/dawarich_db_data`) for an in-app backup feature. The draft drops that mount —
keeping it would give the internet-facing Rails process write access to the raw database
files. The backup feature is the only loss.

## Drafted files

Ready to use once unblocked. `SECRET_KEY_BASE` below already assumes #138's helper; an
earlier draft carried a shell entrypoint wrapper that generated and persisted the secret by
hand, which #138 makes unnecessary.

### `app_meta.json`

```json
{
  "v": "1.2",
  "app_version": "1.15.2",
  "name": "dawarich",
  "pretty_name": "Dawarich",
  "icon": "icon.svg",
  "homepage": "https://dawarich.app",
  "upstream_repo": "https://github.com/Freika/dawarich",
  "entrypoints": [
    { "container_name": "dawarich", "container_port": 3000, "entrypoint_port": "http" }
  ],
  "paths": {
    "": { "access": "private" },
    "/api/v1/owntracks/": { "access": "public" },
    "/api/v1/overland/": { "access": "public" },
    "/api/v1/traccar/": { "access": "public" }
  },
  "minimum_portal_size": "s",
  "lifecycle": { "always_on": true },
  "store_info": {
    "description_short": "Self-hosted replacement for Google Timeline: track, map and analyse your own location history.",
    "description_long": [
      "Dawarich is a self-hosted replacement for Google Timeline. It collects the location history your phone already records, keeps it on your own shard instead of a provider's servers, and gives you an interactive map to explore it: heatmaps, individual points, connecting lines, and a fog-of-war layer that reveals only the parts of the world you have actually visited.",
      "Your phone feeds it through one of the supported tracking apps, such as OwnTracks or Overland. Existing history comes in from a Google Takeout export, from GPX and GeoJSON files, or from the EXIF coordinates embedded in your photos. Everything you put in can be exported again as GeoJSON or GPX, so the data never becomes hostage to the app.",
      "Beyond the map, Dawarich builds trips out of your movements, summarises where and how far you travelled by month and year, and can share a live view with family members on the same instance. Reverse geocoding, which turns coordinates into place names, is optional and off until you point it at a geocoding provider; until you do, no location data leaves your shard."
    ],
    "hint": [
      "Dawarich creates a default account on first start: demo@dawarich.app with the password safepassword. Sign in with it and change both in account settings straight away.",
      "The first start takes a few minutes while the database is prepared and seeded. Later starts are quick.",
      "The tracker ingest endpoints for OwnTracks, Overland and Traccar are reachable from the internet so your phone can submit locations. They are protected by the API key you generate in Dawarich, not by shard pairing. The rest of Dawarich stays private to your paired devices.",
      "Importing a large Google Takeout archive is memory-hungry and can take a while on a small shard."
    ]
  }
}
```

### `docker-compose.yml.template`

```yaml
networks:
    portal:
        external: true
    dawarich:

services:
    dawarich:
        restart: always
        image: freikin/dawarich:1.15.2
        container_name: dawarich
        entrypoint: web-entrypoint.sh
        command: ['bin/rails', 'server', '-p', '3000', '-b', '::']
        volumes:
        - "{{ fs.app_data }}/public:/var/app/public"
        - "{{ fs.app_data }}/storage:/var/app/storage"
        - "{{ fs.app_data }}/watched:/var/app/tmp/imports/watched"
        environment:
        - RAILS_ENV=production
        - SELF_HOSTED=true
        - APPLICATION_HOSTS=dawarich.{{ portal.domain }}
        - APPLICATION_PROTOCOL=https
        - SECRET_KEY_BASE={{ secret('secret_key_base') }}
        - DATABASE_HOST=dawarich-db
        - DATABASE_PORT=5432
        - DATABASE_USERNAME=dawarich
        - DATABASE_PASSWORD={{ secret('db_password') }}
        - DATABASE_NAME=dawarich
        - REDIS_URL=redis://dawarich-redis:6379
        - RAILS_LOG_TO_STDOUT=true
        - STORE_GEODATA=true
        - PROMETHEUS_EXPORTER_ENABLED=false
        - WEB_CONCURRENCY=1
        - TIME_ZONE=Europe/Berlin
        healthcheck:
            test: ["CMD-SHELL", "wget -qO - http://127.0.0.1:3000/api/v1/health | grep -q '\"status\"\\s*:\\s*\"ok\"'"]
            interval: 10s
            retries: 30
            start_period: 30s
            timeout: 10s
        depends_on:
            dawarich-db:
                condition: service_healthy
            dawarich-redis:
                condition: service_healthy
        networks:
        - portal
        - dawarich

    dawarich-sidekiq:
        restart: always
        image: freikin/dawarich:1.15.2
        container_name: dawarich-sidekiq
        entrypoint: sidekiq-entrypoint.sh
        command: ['sidekiq']
        volumes:
        - "{{ fs.app_data }}/public:/var/app/public"
        - "{{ fs.app_data }}/storage:/var/app/storage"
        - "{{ fs.app_data }}/watched:/var/app/tmp/imports/watched"
        environment:
        - RAILS_ENV=production
        - SELF_HOSTED=true
        - APPLICATION_HOSTS=dawarich.{{ portal.domain }}
        - APPLICATION_PROTOCOL=https
        - SECRET_KEY_BASE={{ secret('secret_key_base') }}
        - DATABASE_HOST=dawarich-db
        - DATABASE_PORT=5432
        - DATABASE_USERNAME=dawarich
        - DATABASE_PASSWORD={{ secret('db_password') }}
        - DATABASE_NAME=dawarich
        - REDIS_URL=redis://dawarich-redis:6379
        - RAILS_LOG_TO_STDOUT=true
        - STORE_GEODATA=true
        - PROMETHEUS_EXPORTER_ENABLED=false
        - BACKGROUND_PROCESSING_CONCURRENCY=3
        depends_on:
            dawarich:
                condition: service_healthy
        networks:
        - dawarich

    dawarich-db:
        restart: always
        image: postgis/postgis:17-3.5-alpine
        container_name: dawarich-db
        shm_size: 1G
        volumes:
        - "{{ fs.app_data }}/pgdata:/var/lib/postgresql/data"
        environment:
        - POSTGRES_USER=dawarich
        - POSTGRES_PASSWORD={{ secret('db_password') }}
        - POSTGRES_DB=dawarich
        healthcheck:
            test: ["CMD-SHELL", "pg_isready -U dawarich"]
            interval: 10s
            retries: 5
            start_period: 30s
            timeout: 5s
        networks:
        - dawarich

    dawarich-redis:
        restart: always
        image: redis:7.4-alpine
        container_name: dawarich-redis
        command: redis-server --save 900 1 --save 300 10 --appendonly no
        volumes:
        - "{{ fs.app_data }}/redis:/data"
        healthcheck:
            test: ["CMD", "redis-cli", "ping"]
            interval: 10s
            retries: 5
            start_period: 10s
            timeout: 5s
        networks:
        - dawarich
```

Note the compose above also moves the Postgres password to `{{ secret('db_password') }}`
rather than the hardcoded literal the earlier draft carried — the same helper covers it, and
`app_secrets` is app-scoped so all three services resolve the same value.
