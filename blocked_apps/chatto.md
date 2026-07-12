# Chatto

**Blocked:** 2026-07-12
**Exit code:** reject
**Reason:** Member onboarding is impossible on a shard today (registration hard-requires SMTP; no in-app user creation; operator CLI needs shell). Deliberately deferred until the shard OIDC provider ships — then Chatto becomes a flagship multi-user app.

| Field | Value |
|---|---|
| Homepage | https://chatto.run |
| Upstream repo | https://github.com/chattocorp/chatto |
| License | AGPL-3.0-or-later, Apache-2.0 exceptions for frontend/integration surfaces (foss) |
| Image | ghcr.io/chattocorp/chatto:0.4.7 |
| Description | Team and group chat with voice/video calls and screensharing, free and easy to self-host. |
| Paid | false |
| Auth-proxy | not supported (but OIDC providers with `auto_provision` are) |

## Reason for block

Not a hard platform incompatibility — a deliberate deferral, decided at the ambiguity gate on 2026-07-12:

- Direct registration is email-OTP-first, verified in code (`cli/internal/http_server/auth.go`): without SMTP the endpoint returns 503 "Email delivery is not configured". Shards have no SMTP → nobody can self-register, not even the first owner.
- The first owner CAN be seeded via the operator API (unix socket, `CreateUser` supports `password` + already-verified email); a working single-container integration with a one-shot seeding init container was fully drafted (see below).
- But additional members cannot: the in-app admin API (`AdminUserService`) has no CreateUser, account-invite links don't exist (only room-level joins), and the operator CLI requires `docker exec` — unavailable to shard owners (exit-criterion j territory). Result: Chatto on Freeshard today is owner-only, which defeats a team-chat app's purpose.

**Unblock condition (either):**
1. Freeshard's shard_core OIDC provider (PoC on `spike/oidc-provider-poc`) plus global user management ([FreeshardBase/freeshard#141](https://github.com/FreeshardBase/freeshard/issues/141)) ship. Chatto supports generic OIDC via `[[auth.providers]]` with `auto_provision = true` — account creation by issuer+subject, no email/SMTP needed. `request_email = true` yields provider-verified email claims, which satisfy `CHATTO_OWNERS_EMAILS` owner mapping, so even owner bootstrap moves to SSO.
2. Upstream Chatto adds email-free invite links or in-app admin user creation (project is very young and moving fast — five releases in four days as of blocking; recheck the AdminUserService RPC list and identity docs).

**OIDC integration wrinkles to solve at unblock time:**
- `[[auth.providers]]` entries are repeated TOML sections, likely not expressible as env vars; sidecar files ship verbatim (no `{{ }}` rendering), so the per-shard `issuer_url` can't be a static sidecar. Solution drafted: entrypoint wrapper script renders `/config/chatto.toml` from env at container start.
- OIDC client_id/client_secret registration against the shard IdP depends on the (not yet designed) client-registration mechanism.
- Access mode was left open at the gate ("decide after multi-user is ready"): `public` (external members, mirotalk precedent) vs `private` (household members reach it via paired shard sessions anyway).

## Research notes

Full drafted integration (compose template, app_meta, sidecar scripts, decisions) was completed before the gate; key findings preserved here.

### Identity

`chattocorp/chatto` — Go backend, AGPL-3.0-or-later, 1510 stars, homepage https://chatto.run, docs https://docs.chatto.run. Actively developed (v0.4.7 released 2026-07-11). Commercial entity behind it; self-host is AGPL and free; not accepting outside contributions. Rejected same-name projects: `badoo/Chatto` (Swift iOS chat UI framework), `jaimeteb/chatto` (Go chatbot framework).

### Image

Official backend image `ghcr.io/chattocorp/chatto` (GHCR only; no Docker Hub/quay). Manifest verified for tag `0.4.7`, amd64 + arm64. GitHub release tags carry a `v` prefix, image tags don't → strip `v` (memos pattern in `update_check.py`). Releases are normal (not all-prerelease) → standard `latest_github_release` works. `ghcr.io/chattocorp/chatto-client` is a frontend-only artifact — not needed; the backend image serves the web UI.

### Architecture / drafted deployment

- Single Go binary; persistence is NATS JetStream/KV — no SQL DB. Release image supports embedded NATS (`CHATTO_NATS_EMBEDDED_ENABLED=true`, data in `/data`) → single-container deployment, no supporting services. Resource class xs.
- Listens on HTTP 4000 (`CHATTO_WEBSERVER_PORT`), ConnectRPC + WebSocket. `CHATTO_WEBSERVER_URL=https://chatto.{{ portal.domain }}`.
- Upstream compose's Caddy is redundant behind the shard proxy; LiveKit (voice/video) needs direct UDP 50000-50200 + 3478 — impossible through the proxy → `CHATTO_LIVEKIT_ENABLED=false`, text chat only.
- Image entrypoint (`docker-entrypoint.sh`) does LinuxServer-style PUID/PGID remapping and does NOT chown mounted dirs; default uid 1000 → EACCES on root-owned `fs.app_data` bind mounts → set `PUID=0`/`PGID=0`.
- Image CMD is `start -c /config/chatto.toml`; missing config file is tolerated (env-only config, upstream compose mounts none). Compose `entrypoint:` override clears image CMD — restate `command: ["start", "-c", "/config/chatto.toml"]`.
- Secrets: four 32-byte-hex secrets (`CHATTO_WEBSERVER_COOKIE_SIGNING_SECRET`, `CHATTO_WEBSERVER_COOKIE_ENCRYPTION_SECRET`, `CHATTO_CORE_SECRET_KEY`, `CHATTO_CORE_ASSETS_SIGNING_SECRET`). Static template secrets would allow cookie forgery on every install — drafted a sidecar entrypoint wrapper (`with-secrets.sh`) generating them once into `/data/freeshard/secrets.env` (mode 600), then exec'ing the stock entrypoint. Improves on the librechat static-secret precedent.
- Owner seeding (drafted): one-shot init container (same image, `restart: "no"`), waits for operator socket (`CHATTO_OPERATOR_API_ENABLED=true`, `CHATTO_OPERATOR_API_SOCKET_PATH=/data/freeshard/operator.sock`), runs `/chatto operator user create --login owner --password-stdin --verified-email owner@chatto.{{ portal.domain }}`, writes credentials to `/data/OWNER-CREDENTIALS.txt`. `CHATTO_OWNERS_EMAILS` match on the verified email confers the owner role.
- Registration UI: `CHATTO_AUTH_DIRECT_REGISTRATION=false` hides the (broken-without-SMTP) signup page.
- Lifecycle drafted: `idle_time_for_shutdown: 3600` (convos precedent); `always_on` unjustified with web push off (needs VAPID keys).

### Telemetry

No phone-home/telemetry env var found; metrics and exporter listeners bind localhost by default. Nothing to disable.

### Misc

- Web push optional (`CHATTO_PUSH_ENABLED` + VAPID keys) — left off in draft.
- SSO providers supported: `oidc`, `github`, `gitlab`, `google`, `discord`; upstream even has a Pocket ID guide.
- Very young project (v0.4.x): expect rapid release churn once unblocked.
- Screenshot: https://github.com/user-attachments/assets/a6a8ef8c-9f56-48ed-8740-53115273c22e
