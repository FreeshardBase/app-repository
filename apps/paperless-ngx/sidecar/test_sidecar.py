"""Tests for the paperless-ngx auto-link sidecar.

Run: python3 -m unittest -v (from this directory).

Each test drives reconcile() against a fake that models paperless's user
API and core's owner endpoint, then asserts the side effects (accounts
created, password rotated, email patched) that a real pass would produce.
"""
import base64
import unittest
import unittest.mock
import urllib.error
import urllib.parse

import sidecar


class FakeBackend:
    """Minimal model of paperless's /api/users + core's /internal/owner.

    Authentication is HTTP Basic against the stored password; a login whose
    password does not match a user yields 401, as paperless's basic auth does.
    """

    def __init__(self, users, owner_email, owner_status=200, break_system_create=False):
        # users: list of dicts with username/password/email (id auto-assigned)
        self.users = {}
        self._next_id = 1
        for u in users:
            self._insert(u)
        self.owner_email = owner_email
        self.owner_status = owner_status
        self.break_system_create = break_system_create
        self.calls = []

    def _insert(self, u):
        uid = self._next_id
        self._next_id += 1
        self.users[u["username"].lower()] = {
            "id": uid,
            "username": u["username"],
            "email": u.get("email", ""),
            "password": u["password"],
        }
        return uid

    def _auth_user(self, auth):
        if not auth or not auth.startswith("Basic "):
            return None
        raw = base64.b64decode(auth.split(" ", 1)[1]).decode()
        username, _, password = raw.partition(":")
        user = self.users.get(username.lower())
        if user is not None and user["password"] == password:
            return user
        return None

    def api(self, method, url, auth=None, payload=None):
        self.calls.append((method, url, payload))
        path = url.split("/internal/")[-1] if "/internal/" in url else url

        if url.endswith("/internal/owner"):
            if self.owner_status != 200:
                return self.owner_status, None
            return 200, {"id": 1, "username": "owner", "display_name": "O",
                         "email": self.owner_email}

        # everything else is paperless and needs a valid login
        actor = self._auth_user(auth)
        if actor is None:
            return 401, None

        if "/api/ui_settings/" in url:
            return 200, None

        if "/api/users/?" in url:
            query = urllib.parse.parse_qs(url.split("?", 1)[1])
            wanted = query["username__iexact"][0].lower()
            user = self.users.get(wanted)
            results = [dict(user)] if user else []
            return 200, {"count": len(results), "results": results}

        if method == "POST" and url.endswith("/api/users/"):
            stored_pw = "wrong" if self.break_system_create else payload["password"]
            uid = self._insert({"username": payload["username"],
                                "password": stored_pw,
                                "email": payload.get("email", "")})
            self.users[payload["username"].lower()].update(
                {k: v for k, v in payload.items() if k in ("first_name", "last_name")})
            return 201, {"id": uid}

        if method == "PATCH" and "/api/users/" in url:
            uid = int(url.rstrip("/").rsplit("/", 1)[1])
            target = next(u for u in self.users.values() if u["id"] == uid)
            target.update(payload)
            return 200, None

        return 404, None


def wire(testcase, backend, *, admin_pw="admin", system_pw="syssecret"):
    testcase.patch("_api", backend.api)
    testcase.patch("ADMIN_PASSWORD", admin_pw)
    testcase.patch("SYSTEM_PASSWORD", system_pw)
    testcase.patch("ADMIN_USERNAME", "admin")
    testcase.patch("SYSTEM_USERNAME", "freeshard-system")


class ReconcileTest(unittest.TestCase):
    def patch(self, name, value):
        original = getattr(sidecar, name)
        self.addCleanup(setattr, sidecar, name, original)
        setattr(sidecar, name, value)

    def test_existing_shard_bootstraps_system_rotates_and_sets_email(self):
        # admin/admin, never rotated; system account absent; owner verified.
        backend = FakeBackend(
            users=[{"username": "admin", "password": "admin", "email": ""}],
            owner_email="owner@example.com",
        )
        wire(self, backend, admin_pw="newsecret")
        sidecar.reconcile()
        self.assertIn("freeshard-system", backend.users)
        system = backend.users["freeshard-system"]
        self.assertEqual(system["password"], "syssecret")
        self.assertEqual(system["last_name"], "system account, do not delete")
        self.assertEqual(backend.users["admin"]["password"], "newsecret")
        self.assertEqual(backend.users["admin"]["email"], "owner@example.com")

    def test_rotation_skipped_when_admin_already_rotated(self):
        # admin already on the secret; system still needs creating.
        backend = FakeBackend(
            users=[{"username": "admin", "password": "newsecret", "email": "owner@example.com"}],
            owner_email="owner@example.com",
        )
        wire(self, backend, admin_pw="newsecret")
        sidecar.reconcile()
        patches = [c for c in backend.calls if c[0] == "PATCH"]
        self.assertEqual(patches, [], "nothing should be patched on a converged shard")

    def test_null_owner_email_leaves_admin_unchanged(self):
        backend = FakeBackend(
            users=[{"username": "admin", "password": "newsecret", "email": ""}],
            owner_email=None,
        )
        wire(self, backend, admin_pw="newsecret")
        sidecar.reconcile()
        email_patches = [c for c in backend.calls
                         if c[0] == "PATCH" and c[2] and "email" in c[2]]
        self.assertEqual(email_patches, [])
        self.assertEqual(backend.users["admin"]["email"], "")

    def test_email_patched_only_on_mismatch(self):
        # system exists already; admin email stale -> exactly one email patch.
        backend = FakeBackend(
            users=[
                {"username": "admin", "password": "newsecret", "email": "old@example.com"},
                {"username": "freeshard-system", "password": "syssecret"},
            ],
            owner_email="owner@example.com",
        )
        wire(self, backend, admin_pw="newsecret")
        sidecar.reconcile()
        email_patches = [c for c in backend.calls
                         if c[0] == "PATCH" and c[2] and "email" in c[2]]
        self.assertEqual(len(email_patches), 1)
        self.assertEqual(backend.users["admin"]["email"], "owner@example.com")

    def test_system_account_patches_as_itself_not_admin(self):
        # After the owner's OIDC login wipes admin's password, admin cannot
        # log in at all; the sidecar must still work via the system account.
        backend = FakeBackend(
            users=[
                {"username": "admin", "password": "!wiped!", "email": "old@example.com"},
                {"username": "freeshard-system", "password": "syssecret"},
            ],
            owner_email="owner@example.com",
        )
        wire(self, backend, admin_pw="newsecret")
        sidecar.reconcile()
        self.assertEqual(backend.users["admin"]["email"], "owner@example.com")

    def test_bootstrap_fails_cleanly_when_no_admin_login_works(self):
        # admin password wiped and system absent: a RuntimeError, not a crash.
        backend = FakeBackend(
            users=[{"username": "admin", "password": "!wiped!", "email": "old@example.com"}],
            owner_email="owner@example.com",
        )
        wire(self, backend, admin_pw="newsecret")
        with self.assertRaises(RuntimeError):
            sidecar.reconcile()

    def test_transport_error_propagates_for_retry(self):
        def boom(*a, **k):
            raise urllib.error.URLError("connection refused")
        self.patch("_api", boom)
        self.patch("SYSTEM_PASSWORD", "syssecret")
        with self.assertRaises(urllib.error.URLError):
            sidecar.reconcile()

    def test_system_account_created_but_unauthenticatable_raises(self):
        backend = FakeBackend(
            users=[{"username": "admin", "password": "admin", "email": ""}],
            owner_email="owner@example.com",
            break_system_create=True,
        )
        wire(self, backend, admin_pw="newsecret")
        with self.assertRaises(RuntimeError):
            sidecar.reconcile()

    def test_non_json_200_is_raised_as_runtimeerror(self):
        # _api must not let a JSONDecodeError escape uncaught; main() only
        # catches URLError/OSError/RuntimeError, so it is surfaced as the last.
        class FakeResp:
            status = 200
            def read(self):
                return b"<html>not json</html>"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        self.patch("SYSTEM_PASSWORD", "syssecret")
        with unittest.mock.patch("urllib.request.urlopen", return_value=FakeResp()):
            with self.assertRaises(RuntimeError):
                sidecar._api("GET", "http://x/internal/owner")


if __name__ == "__main__":
    unittest.main()
