#!/usr/bin/env python3
"""Paperless-ngx auto-link sidecar (long-lived).

Keeps paperless's ``admin`` account aligned with the shard owner so the
owner's OIDC login matches it by verified email, and retires the shared
``admin``/``admin`` credential on shards that predate the rotation. It talks
only to paperless's own REST API and core's ``/internal/owner`` endpoint,
never to ``manage.py`` or the database.

Each reconcile pass, in order:

1. Ensure a dedicated ``freeshard-system`` superuser exists, bootstrapping
   it once by logging in as ``admin`` (per-shard secret first, then the
   legacy ``admin``/``admin`` for shards that have never rotated). All later
   work runs as that account, which survives the owner's first OIDC login
   wiping ``admin``'s password.
2. Rotate ``admin``'s password to the per-shard secret while it is still the
   default. This is what reaches shards that already existed before the
   compose-level rotation, which only takes effect on fresh installs.
3. Set ``admin``'s email to the owner's verified email (``/internal/owner``),
   leaving it unchanged when the owner has no verified address.

Every step is GET-compare-PATCH: a pass that finds nothing to change is a
clean pass, so repeating it is safe. stdlib only, per the sidecar contract.
"""
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("paperless-sidecar")

PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "http://paperless-ngx:8000").rstrip("/")
# shard_core is the core container's name on the shared `portal` network.
CORE_URL = os.environ.get("CORE_URL", "http://shard_core").rstrip("/")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
SYSTEM_USERNAME = os.environ.get("SYSTEM_USERNAME", "freeshard-system")
SYSTEM_PASSWORD = os.environ.get("SYSTEM_PASSWORD", "")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
HTTP_TIMEOUT = 10


def _basic(username: str, password: str) -> str:
    token = b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def _api(method: str, url: str, auth: str | None = None, payload: dict | None = None):
    """Call a JSON endpoint.

    Returns ``(status_code, parsed_body_or_None)``. An HTTP error status
    (401, 404, 500, ...) is returned as the status, not raised, so callers
    can branch on it. A transport failure (host unreachable, timeout) raises
    ``URLError``/``OSError`` for the pass to treat as a transient error.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if auth is not None:
        headers["Authorization"] = auth
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {url}: {exc}") from exc


def _authenticates(auth: str) -> bool:
    status, _ = _api("GET", f"{PAPERLESS_URL}/api/ui_settings/", auth)
    return status == 200


def _get_user(auth: str, username: str) -> dict | None:
    """Return the paperless user row for ``username``, or None if absent.

    Looked up by ``username__iexact``: the id is not reliably 1 (a consumer
    and a django-guardian AnonymousUser row also exist) and there is no plain
    exact-match filter.
    """
    query = urllib.parse.urlencode({"username__iexact": username})
    status, body = _api("GET", f"{PAPERLESS_URL}/api/users/?{query}", auth)
    if status != 200 or not body:
        return None
    results = body.get("results") or []
    return results[0] if results else None


def _patch_user(auth: str, user_id: int, fields: dict) -> None:
    status, _ = _api("PATCH", f"{PAPERLESS_URL}/api/users/{user_id}/", auth, fields)
    if status != 200:
        raise RuntimeError(f"PATCH /api/users/{user_id}/ returned HTTP {status}")


def _bootstrap_admin_auth() -> str | None:
    """Find a working ``admin`` login to create the system account with.

    Tries the per-shard secret first, then the legacy ``admin``/``admin`` for
    shards that have never rotated. Returns None when neither works (e.g. the
    owner's OIDC login has already wiped admin's password).
    """
    passwords = [ADMIN_PASSWORD]
    if ADMIN_PASSWORD != "admin":
        passwords.append("admin")
    for password in passwords:
        auth = _basic(ADMIN_USERNAME, password)
        if _authenticates(auth):
            return auth
    return None


def _ensure_system_account(system_auth: str) -> str:
    """Return a working auth for the system account, creating it if needed."""
    if _authenticates(system_auth):
        return system_auth
    admin_auth = _bootstrap_admin_auth()
    if admin_auth is None:
        raise RuntimeError("no working admin login to bootstrap the system account")
    payload = {
        "username": SYSTEM_USERNAME,
        "password": SYSTEM_PASSWORD,
        "is_superuser": True,
        "is_active": True,
        "first_name": "Freeshard",
        "last_name": "system account, do not delete",
    }
    status, _ = _api("POST", f"{PAPERLESS_URL}/api/users/", admin_auth, payload)
    if status not in (200, 201):
        raise RuntimeError(f"POST /api/users/ for system account returned HTTP {status}")
    if not _authenticates(system_auth):
        raise RuntimeError("system account was created but cannot authenticate")
    log.info("created the %s superuser", SYSTEM_USERNAME)
    return system_auth


def _rotate_admin_password(system_auth: str) -> None:
    if ADMIN_PASSWORD == "admin":
        return
    if not _authenticates(_basic(ADMIN_USERNAME, "admin")):
        return
    admin = _get_user(system_auth, ADMIN_USERNAME)
    if admin is None:
        raise RuntimeError("admin user not found while rotating password")
    _patch_user(system_auth, admin["id"], {"password": ADMIN_PASSWORD})
    log.info("rotated the admin password to the per-shard secret")


def _fetch_owner_email() -> str | None:
    """Return the owner's verified email, or None when there is none yet."""
    status, body = _api("GET", f"{CORE_URL}/internal/owner")
    if status == 404:
        return None
    if status != 200 or body is None:
        raise RuntimeError(f"GET /internal/owner returned HTTP {status}")
    return body.get("email")


def _sync_admin_email(system_auth: str) -> None:
    owner_email = _fetch_owner_email()
    if not owner_email:
        log.info("owner has no verified email yet; leaving admin email unchanged")
        return
    admin = _get_user(system_auth, ADMIN_USERNAME)
    if admin is None:
        raise RuntimeError("admin user not found while syncing email")
    if admin.get("email") == owner_email:
        log.info("admin email already matches the owner's verified email; nothing to do")
        return
    _patch_user(system_auth, admin["id"], {"email": owner_email})
    log.info("set admin email to the owner's verified email")


def reconcile() -> None:
    system_auth = _ensure_system_account(_basic(SYSTEM_USERNAME, SYSTEM_PASSWORD))
    _rotate_admin_password(system_auth)
    _sync_admin_email(system_auth)


def main() -> int:
    if not SYSTEM_PASSWORD:
        log.error("SYSTEM_PASSWORD is not set; refusing to run")
        return 1
    while True:
        try:
            reconcile()
        except (urllib.error.URLError, OSError) as exc:
            log.error("paperless or core unreachable this pass: %s", exc)
        except RuntimeError as exc:
            log.error("reconcile pass failed: %s", exc)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
