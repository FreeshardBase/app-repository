#!/usr/bin/env python3
"""Immich OIDC auto-link sidecar (long-lived).

Makes the shard owner's first OIDC sign-in attach to their existing Immich
account instead of creating a new one. Immich links an OIDC identity to a
local account by *verified email* on the first login only, so the account's
email has to already equal the owner's verified email before they log in.

Each reconcile pass, in order:

1. Ensure a dedicated ``freeshard-system`` admin account exists and log in as
   it. All later work runs as that account, which Freeshard controls and the
   owner's OIDC login never touches. Bootstrapping it has two shapes:
     - fresh install (no users yet): create it via ``POST /api/auth/admin-sign-up``;
     - already-provisioned shard (the owner's account already exists): a
       one-shot DB job (see the compose template) has seeded a throwaway admin
       API key; authenticate with it, create ``freeshard-system``, then delete
       the seeded key again. This is the single step that does not go through
       Immich's API; everything else does.
2. Push the OIDC settings into Immich's stored system config (the ``oauth``
   section only), so Immich advertises the shard as an OIDC provider.
3. Reconcile the owner's Immich account: on a fresh install create it from the
   owner's verified email; otherwise set the existing account's email to the
   verified one. Also keep the ``admin`` storage label on the owner's account,
   not on ``freeshard-system``.

Every step is GET-compare-write: a pass that finds nothing to change is a
clean pass, so repeating it is safe. stdlib only, per the sidecar contract.
"""
import json
import logging
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("immich-sidecar")

IMMICH_URL = os.environ.get("IMMICH_URL", "http://immich_server:2283").rstrip("/")
# shard_core is the core container's name on the shared `portal` network.
CORE_URL = os.environ.get("CORE_URL", "http://shard_core").rstrip("/")
SYSTEM_EMAIL = os.environ.get("SYSTEM_EMAIL", "freeshard-system@system.freeshard.net")
SYSTEM_PASSWORD = os.environ.get("SYSTEM_PASSWORD", "")
SYSTEM_NAME = os.environ.get("SYSTEM_NAME", "Freeshard system account, do not delete")
# Raw secret for the DB-seeded bootstrap API key (empty when none was seeded).
BOOTSTRAP_API_KEY = os.environ.get("BOOTSTRAP_API_KEY", "")
# Name the DB job gives the seeded key, used to find and delete it again.
BOOTSTRAP_KEY_NAME = os.environ.get("BOOTSTRAP_KEY_NAME", "freeshard-bootstrap")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
# The owner's account must own this storage label so its library bind-mounts
# to the shard's shared `pictures` folder (admin-sign-up assigns it to the
# first account created, which on a fresh install is freeshard-system).
STORAGE_LABEL = os.environ.get("STORAGE_LABEL", "admin")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
HTTP_TIMEOUT = 10


def _api(method: str, url: str, headers: dict | None = None, payload: dict | None = None):
    """Call a JSON endpoint.

    Returns ``(status_code, parsed_body_or_None)``. An HTTP error status
    (400, 401, 404, ...) is returned as the status, not raised, so callers can
    branch on it. A transport failure (host unreachable, timeout) raises
    ``URLError``/``OSError`` for the pass to treat as transient. A 2xx body
    that is not JSON raises ``RuntimeError`` rather than crashing the loop.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {url}: {exc}") from exc


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _apikey(secret: str) -> dict:
    return {"x-api-key": secret}


def _login(email: str, password: str) -> str | None:
    """Return an access token for ``email``/``password``, or None if refused."""
    status, body = _api("POST", f"{IMMICH_URL}/api/auth/login",
                        payload={"email": email, "password": password})
    if status in (200, 201) and body and body.get("accessToken"):
        return body["accessToken"]
    return None


def _is_admin_authenticated(headers: dict) -> bool:
    status, _ = _api("GET", f"{IMMICH_URL}/api/admin/users", headers)
    return status == 200


def _admin_sign_up(email: str, password: str, name: str) -> bool:
    """Create the very first admin via the setup endpoint.

    Succeeds only while Immich has zero users; returns False once an admin
    already exists (an already-provisioned shard), so the caller falls through
    to the DB-seeded-key path.
    """
    status, _ = _api("POST", f"{IMMICH_URL}/api/auth/admin-sign-up",
                     payload={"email": email, "password": password, "name": name})
    return status in (200, 201)


def _list_users(headers: dict) -> list:
    status, body = _api("GET", f"{IMMICH_URL}/api/admin/users", headers)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/users returned HTTP {status}")
    return body or []


def _create_admin_user(headers: dict, email: str, password: str, name: str,
                       storage_label: str | None = None) -> None:
    payload = {
        "email": email,
        "password": password,
        "name": name,
        "isAdmin": True,
        "shouldChangePassword": False,
    }
    if storage_label is not None:
        payload["storageLabel"] = storage_label
    status, _ = _api("POST", f"{IMMICH_URL}/api/admin/users", headers, payload)
    if status not in (200, 201):
        raise RuntimeError(f"POST /api/admin/users for {email} returned HTTP {status}")


def _update_user(headers: dict, user_id: str, fields: dict) -> None:
    status, _ = _api("PUT", f"{IMMICH_URL}/api/admin/users/{user_id}", headers, fields)
    if status not in (200, 201):
        raise RuntimeError(f"PUT /api/admin/users/{user_id} returned HTTP {status}")


def _delete_bootstrap_key(headers: dict) -> None:
    """Delete the DB-seeded bootstrap API key, if it is still present.

    ``headers`` must authenticate as the key's owner (the pre-existing admin),
    since Immich scopes ``/api/api-keys`` to the calling identity.
    """
    status, body = _api("GET", f"{IMMICH_URL}/api/api-keys", headers)
    if status != 200 or not body:
        return
    for key in body:
        if key.get("name") == BOOTSTRAP_KEY_NAME:
            _api("DELETE", f"{IMMICH_URL}/api/api-keys/{key['id']}", headers)
            log.info("deleted the DB-seeded bootstrap API key")


def _cleanup_bootstrap_key() -> None:
    """Best-effort removal of a lingering bootstrap key once freeshard-system exists.

    Covers the case where a previous pass created freeshard-system but died
    before deleting the seeded key.
    """
    if not BOOTSTRAP_API_KEY:
        return
    apikey = _apikey(BOOTSTRAP_API_KEY)
    if _is_admin_authenticated(apikey):
        _delete_bootstrap_key(apikey)


def _ensure_system_auth() -> dict:
    """Return auth headers for freeshard-system, bootstrapping it if needed."""
    token = _login(SYSTEM_EMAIL, SYSTEM_PASSWORD)
    if token:
        _cleanup_bootstrap_key()
        return _bearer(token)

    # Already-provisioned shard: use the DB-seeded admin API key.
    if BOOTSTRAP_API_KEY:
        apikey = _apikey(BOOTSTRAP_API_KEY)
        if _is_admin_authenticated(apikey):
            _create_admin_user(apikey, SYSTEM_EMAIL, SYSTEM_PASSWORD, SYSTEM_NAME)
            _delete_bootstrap_key(apikey)
            token = _login(SYSTEM_EMAIL, SYSTEM_PASSWORD)
            if not token:
                raise RuntimeError("freeshard-system created via the DB key but cannot log in")
            log.info("bootstrapped freeshard-system via the DB-seeded API key")
            return _bearer(token)

    # Fresh install: claim the first-admin slot.
    if _admin_sign_up(SYSTEM_EMAIL, SYSTEM_PASSWORD, SYSTEM_NAME):
        token = _login(SYSTEM_EMAIL, SYSTEM_PASSWORD)
        if not token:
            raise RuntimeError("freeshard-system created via admin-sign-up but cannot log in")
        log.info("bootstrapped freeshard-system via admin-sign-up (fresh install)")
        return _bearer(token)

    raise RuntimeError("cannot bootstrap freeshard-system: no working DB key and admin-sign-up refused")


def _reconcile_oauth(headers: dict) -> None:
    if not (OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET):
        log.info("OIDC client not configured (issuer/client id/secret missing); leaving oauth config untouched")
        return
    status, config = _api("GET", f"{IMMICH_URL}/api/system-config", headers)
    if status != 200 or config is None:
        raise RuntimeError(f"GET /api/system-config returned HTTP {status}")
    current = dict(config.get("oauth") or {})
    desired = dict(current)
    desired.update({
        "enabled": True,
        "issuerUrl": OIDC_ISSUER,
        "clientId": OIDC_CLIENT_ID,
        "clientSecret": OIDC_CLIENT_SECRET,
        "autoRegister": False,
        "autoLaunch": True,
    })
    if desired == current:
        log.info("OIDC system-config already matches desired; nothing to do")
        return
    config["oauth"] = desired
    status, _ = _api("PUT", f"{IMMICH_URL}/api/system-config", headers, config)
    if status not in (200, 201):
        raise RuntimeError(f"PUT /api/system-config returned HTTP {status}")
    log.info("updated the OIDC (oauth) system-config section")


def _fetch_owner() -> dict | None:
    """Return core's owner record, or None when no owner is provisioned yet.

    The record carries a verified-or-``null`` ``email`` per freeshard#307.
    """
    status, body = _api("GET", f"{CORE_URL}/internal/owner")
    if status == 404:
        return None
    if status != 200 or body is None:
        raise RuntimeError(f"GET /internal/owner returned HTTP {status}")
    return body


def _find_by_email(users: list, email: str) -> dict | None:
    lowered = email.lower()
    for user in users:
        if (user.get("email") or "").lower() == lowered:
            return user
    return None


def _reconcile_owner_account(headers: dict) -> None:
    users = _list_users(headers)
    system = _find_by_email(users, SYSTEM_EMAIL)
    others = [u for u in users if (u.get("email") or "").lower() != SYSTEM_EMAIL.lower()]

    # The reserved storage label has to live on the owner's account, so take
    # it off freeshard-system first (admin-sign-up put it there on a fresh
    # install) before assigning it below; Immich requires labels to be unique.
    if system and system.get("storageLabel") == STORAGE_LABEL:
        _update_user(headers, system["id"], {"storageLabel": None})
        log.info("cleared the %r storage label from freeshard-system", STORAGE_LABEL)

    owner = _fetch_owner()
    owner_email = (owner or {}).get("email")

    if len(others) == 0:
        if owner_email:
            name = (owner.get("name") or owner.get("display_name")
                    or owner.get("username") or owner_email)
            _create_admin_user(headers, owner_email, secrets.token_urlsafe(32), name,
                               storage_label=STORAGE_LABEL)
            log.info("created the owner's Immich account with the verified email and %r storage label",
                     STORAGE_LABEL)
        else:
            log.info("no owner account yet and owner has no verified email; nothing to create")
        return

    if len(others) > 1:
        log.info("multiple non-system users present; multi-user shards are out of scope, skipping owner reconcile")
        return

    owner_account = others[0]
    patch: dict = {}
    if owner_email and (owner_account.get("email") or "") != owner_email:
        patch["email"] = owner_email
    if owner_account.get("storageLabel") != STORAGE_LABEL:
        patch["storageLabel"] = STORAGE_LABEL
    if not patch:
        log.info("owner account already matches the owner's verified email and storage label; nothing to do")
        return
    _update_user(headers, owner_account["id"], patch)
    log.info("updated owner account fields: %s", ", ".join(sorted(patch)))


def reconcile() -> None:
    headers = _ensure_system_auth()
    _reconcile_oauth(headers)
    _reconcile_owner_account(headers)


def main() -> int:
    if not SYSTEM_PASSWORD:
        log.error("SYSTEM_PASSWORD is not set; refusing to run")
        return 1
    while True:
        try:
            reconcile()
        except (urllib.error.URLError, OSError) as exc:
            log.error("immich or core unreachable this pass: %s", exc)
        except RuntimeError as exc:
            log.error("reconcile pass failed: %s", exc)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
