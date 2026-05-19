# Fizzy

**Blocked:** 2026-05-18
**Exit code:** b
**Reason:** Source-available license (O'Saasy) — not FOSS.

| Field | Value |
|---|---|
| Homepage | https://fizzy.do |
| Upstream repo | https://github.com/basecamp/fizzy |
| License | O'Saasy License (source-available) |
| Image | `ghcr.io/basecamp/fizzy:main` (multi-arch manifest verified) |
| Description | Kanban tracking tool for issues and ideas by 37signals |
| Paid | false (free for personal/team self-host) |
| Auth-proxy | not supported (email-code sign-in only) |

## Reason for block

Fizzy is released under 37signals' O'Saasy License. The license permits
self-hosting for personal or team use but forbids redistributing or
reselling the software as a competing hosted service. Per
`.claude/skills/add-app/reference/exit-criteria.md`, any
`license_class ∈ {source-available, proprietary}` is a hard exit (code
`b`). The license is not in the FOSS set (MIT, Apache-2.0, BSD-*,
GPL-*, AGPL-3.0, LGPL-*, MPL-2.0, ISC, Unlicense, CC0-1.0) and is not
OSI-approved.

The app itself is otherwise a strong fit: an official Docker image
exists at `ghcr.io/basecamp/fizzy:main`, the project is actively
maintained (last release 2026-05-15), single-tenant by default, and
runs on a single SQLite-backed container with no supporting services.
The only deployment friction is the lack of auth-proxy support — users
would sign in via Fizzy's own email verification code flow rather than
Freeshard's paired-device identity.

## Research notes

### Auth-proxy support
No built-in reverse-proxy header auth. Sign-in is by email (6-digit
verification code, delivered via SMTP or readable from container logs).
No documented `REMOTE_USER` / `X-Forwarded-User` env vars. Behind a
reverse proxy, set `DISABLE_SSL=true` and
`BASE_URL=https://<shard-domain>` so generated links are correct.

### Shared volume hints
Storage is a single path: `/rails/storage` (SQLite DB + Active Storage
uploads). No music/photo/document conventions apply.

### Telemetry opt-out
No telemetry env vars documented; no Sentry/PostHog references in the
deployment guide. Likely no outbound telemetry but not explicitly
stated.

### Alternative image candidates considered and rejected
- Docker Hub `basecamp/fizzy` — README points exclusively to GHCR.
- `foxnne/fizzy` — Zig desktop pixel-art editor, not a web app.
- `wasmx/fizzy` — Wasm interpreter C++ library.
- `huangyuzhang/Fizzy-Theme`, `jglovier/fizzy` — themes, not apps.
- `basecamp/fizzy-saas` — hosted SaaS variant, not for self-hosting.

### Deployment quirks
- Kamal-proxy inside the container binds 80/443 by default; needs
  `DISABLE_SSL=true` behind a reverse proxy.
- Single-tenant by default; signup closes after first account creation.
- SQLite-only (no Postgres toggle exposed in docs).
- Rolling `main` tag — no semver releases, pin via digest if used.
- Required env: `SECRET_KEY_BASE`, `BASE_URL`; optional SMTP and
  VAPID Web Push keys.

### When to reconsider

If 37signals relicenses Fizzy under an OSI-approved license, delete
this file and re-run `/add-app fizzy`.
