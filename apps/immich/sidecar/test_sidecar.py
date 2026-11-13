"""Tests for the Immich OIDC auto-link sidecar.

Run: python3 -m unittest -v (from this directory).

Each test drives reconcile() against a fake that models the slice of Immich's
API the sidecar uses (auth, admin users, system config, API keys) plus core's
owner endpoint, then asserts the side effects (accounts created, email set,
storage label moved, oauth config pushed) that a real pass would produce.
"""
import base64
import unittest
import unittest.mock
import urllib.error

import sidecar


class FakeImmich:
    """Models Immich's /api/* plus core's /internal/owner.

    Auth: a Bearer token minted by login, or the seeded bootstrap API key via
    x-api-key. A request to an admin endpoint without a valid admin identity
    yields 401, as Immich's guard does.
    """

    def __init__(self, users=None, owner=None, owner_status=200,
                 bootstrap_key=None, break_system_create=False):
        self.users = {}
        self._next_id = 1
        for u in (users or []):
            self._insert(u)
        self.owner = owner
        self.owner_status = owner_status
        # bootstrap_key: the raw secret that authenticates as the first admin.
        self.bootstrap_key = bootstrap_key
        self.api_keys = []
        if bootstrap_key is not None:
            admin = next((u for u in self.users.values() if u["isAdmin"]), None)
            if admin is not None:
                self.api_keys.append({"id": "bk1", "name": sidecar.BOOTSTRAP_KEY_NAME,
                                      "secret": bootstrap_key, "userId": admin["id"]})
        self.break_system_create = break_system_create
        self.system_config = {"oauth": {"enabled": False, "issuerUrl": "", "clientId": "",
                                        "clientSecret": "", "autoRegister": True, "autoLaunch": False,
                                        "buttonText": "Login with OAuth"},
                              "ffmpeg": {"crf": 23}}
        self.tokens = {}
        self._next_token = 1
        self.calls = []

    def _insert(self, u):
        uid = u.get("id") or f"u{self._next_id}"
        self._next_id += 1
        self.users[uid] = {
            "id": uid,
            "email": u["email"],
            "name": u.get("name", ""),
            "password": u["password"],
            "isAdmin": u.get("isAdmin", False),
            "storageLabel": u.get("storageLabel"),
        }
        return uid

    def _identity(self, headers):
        """Return (user, is_admin) for the request's auth, or (None, False)."""
        headers = headers or {}
        auth = headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            user = self.tokens.get(auth.split(" ", 1)[1])
            return (user, user["isAdmin"]) if user else (None, False)
        apikey = headers.get("x-api-key")
        if apikey and apikey == self.bootstrap_key:
            admin = next((u for u in self.users.values() if u["isAdmin"]), None)
            return (admin, True) if admin else (None, False)
        return (None, False)

    def api(self, method, url, headers=None, payload=None):
        self.calls.append((method, url, payload))

        if url.endswith("/internal/owner"):
            if self.owner_status != 200:
                return self.owner_status, None
            return 200, self.owner

        if url.endswith("/api/auth/login"):
            user = next((u for u in self.users.values()
                         if u["email"] == payload["email"] and u["password"] == payload["password"]), None)
            if user is None:
                return 401, None
            token = f"tok{self._next_token}"
            self._next_token += 1
            self.tokens[token] = user
            return 201, {"accessToken": token, "userId": user["id"], "isAdmin": user["isAdmin"]}

        if url.endswith("/api/auth/admin-sign-up"):
            if any(u["isAdmin"] for u in self.users.values()):
                return 400, None
            uid = self._insert({"email": payload["email"], "password": payload["password"],
                                "name": payload["name"], "isAdmin": True, "storageLabel": "admin"})
            return 201, {"id": uid}

        user, is_admin = self._identity(headers)

        if url.endswith("/api/admin/users") and method == "GET":
            if not is_admin:
                return 401, None
            return 200, [dict(u) for u in self.users.values()]

        if url.endswith("/api/admin/users") and method == "POST":
            if not is_admin:
                return 401, None
            stored_pw = "wrong" if self.break_system_create else payload["password"]
            uid = self._insert({"email": payload["email"], "password": stored_pw,
                                "name": payload.get("name", ""), "isAdmin": payload.get("isAdmin", False),
                                "storageLabel": payload.get("storageLabel")})
            return 201, {"id": uid}

        if "/api/admin/users/" in url and method == "PUT":
            if not is_admin:
                return 401, None
            uid = url.rstrip("/").rsplit("/", 1)[1]
            self.users[uid].update({k: v for k, v in payload.items()
                                    if k in ("email", "storageLabel", "name")})
            return 200, dict(self.users[uid])

        if url.endswith("/api/system-config") and method == "GET":
            if not is_admin:
                return 401, None
            return 200, {k: (dict(v) if isinstance(v, dict) else v)
                         for k, v in self.system_config.items()}

        if url.endswith("/api/system-config") and method == "PUT":
            if not is_admin:
                return 401, None
            self.system_config = payload
            return 200, payload

        if url.endswith("/api/api-keys") and method == "GET":
            if user is None:
                return 401, None
            return 200, [{"id": k["id"], "name": k["name"]}
                         for k in self.api_keys if k["userId"] == user["id"]]

        if "/api/api-keys/" in url and method == "DELETE":
            if user is None:
                return 401, None
            kid = url.rstrip("/").rsplit("/", 1)[1]
            self.api_keys = [k for k in self.api_keys if k["id"] != kid]
            return 200, None

        return 404, None


def oauth(backend):
    return backend.system_config["oauth"]


def non_system(backend):
    return [u for u in backend.users.values() if u["email"] != sidecar.SYSTEM_EMAIL]


class ReconcileTest(unittest.TestCase):
    def patch(self, name, value):
        original = getattr(sidecar, name)
        self.addCleanup(setattr, sidecar, name, original)
        setattr(sidecar, name, value)

    def wire(self, backend, *, system_pw="syssecret", bootstrap_key="", oidc=True):
        self.patch("_api", backend.api)
        self.patch("SYSTEM_PASSWORD", system_pw)
        self.patch("SYSTEM_EMAIL", "freeshard-system@system.freeshard.net")
        self.patch("BOOTSTRAP_API_KEY", bootstrap_key)
        self.patch("STORAGE_LABEL", "admin")
        if oidc:
            self.patch("OIDC_ISSUER", "https://idp.shard.example")
            self.patch("OIDC_CLIENT_ID", "cid")
            self.patch("OIDC_CLIENT_SECRET", "csecret")

    # --- fresh install -----------------------------------------------------

    def test_fresh_install_signs_up_system_and_creates_owner(self):
        backend = FakeImmich(users=[], owner={"email": "owner@example.com", "name": "Owner"})
        self.wire(backend)
        sidecar.reconcile()

        system = sidecar._find_by_email(list(backend.users.values()), sidecar.SYSTEM_EMAIL)
        self.assertIsNotNone(system)
        self.assertTrue(system["isAdmin"])
        # The reserved label must have moved off freeshard-system onto the owner.
        self.assertNotEqual(system["storageLabel"], "admin")
        owners = non_system(backend)
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0]["email"], "owner@example.com")
        self.assertEqual(owners[0]["storageLabel"], "admin")
        self.assertTrue(owners[0]["isAdmin"])
        self.assertEqual(oauth(backend)["enabled"], True)
        self.assertEqual(oauth(backend)["autoRegister"], False)
        self.assertEqual(oauth(backend)["autoLaunch"], True)
        self.assertEqual(oauth(backend)["issuerUrl"], "https://idp.shard.example")

    def test_fresh_install_without_verified_email_creates_no_owner(self):
        backend = FakeImmich(users=[], owner=None, owner_status=404)
        self.wire(backend)
        sidecar.reconcile()
        self.assertEqual(non_system(backend), [])
        # oauth is still configured even before the owner has an account.
        self.assertEqual(oauth(backend)["enabled"], True)

    # --- already-provisioned shard ----------------------------------------

    def test_existing_shard_bootstraps_via_db_key_and_sets_owner_email(self):
        backend = FakeImmich(
            users=[{"email": "someone@gmail.com", "password": "ownerchosen",
                    "isAdmin": True, "storageLabel": "admin"}],
            owner={"email": "owner@example.com", "name": "Owner"},
            bootstrap_key="rawkey",
        )
        self.wire(backend, bootstrap_key="rawkey")
        sidecar.reconcile()

        self.assertIsNotNone(sidecar._find_by_email(list(backend.users.values()), sidecar.SYSTEM_EMAIL))
        owners = non_system(backend)
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0]["email"], "owner@example.com")
        self.assertEqual(owners[0]["storageLabel"], "admin")
        # The seeded bootstrap key must be gone afterwards.
        self.assertEqual(backend.api_keys, [])

    def test_existing_shard_without_db_key_raises(self):
        backend = FakeImmich(
            users=[{"email": "someone@gmail.com", "password": "ownerchosen", "isAdmin": True}],
            owner={"email": "owner@example.com"},
            bootstrap_key=None,
        )
        self.wire(backend, bootstrap_key="rawkey")  # sidecar has a secret, but DB has no matching row
        with self.assertRaises(RuntimeError):
            sidecar.reconcile()

    def test_lingering_bootstrap_key_is_cleaned_up(self):
        # freeshard-system already exists (login works) but a prior pass died
        # before deleting the seeded key.
        backend = FakeImmich(
            users=[
                {"email": "someone@gmail.com", "password": "ownerchosen",
                 "isAdmin": True, "storageLabel": "admin"},
                {"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                 "isAdmin": True},
            ],
            owner={"email": "owner@example.com"},
            bootstrap_key="rawkey",
        )
        self.wire(backend, bootstrap_key="rawkey")
        sidecar.reconcile()
        self.assertEqual(backend.api_keys, [])

    # --- owner email reconcile --------------------------------------------

    def test_owner_email_patched_only_on_mismatch(self):
        backend = FakeImmich(
            users=[
                {"email": "stale@old.com", "password": "ownerchosen",
                 "isAdmin": True, "storageLabel": "admin"},
                {"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                 "isAdmin": True},
            ],
            owner={"email": "owner@example.com"},
        )
        self.wire(backend)
        sidecar.reconcile()
        owners = non_system(backend)
        self.assertEqual(owners[0]["email"], "owner@example.com")
        email_puts = [c for c in backend.calls
                      if c[0] == "PUT" and "/api/admin/users/" in c[1] and c[2] and "email" in c[2]]
        self.assertEqual(len(email_puts), 1)

    def test_converged_shard_writes_nothing(self):
        backend = FakeImmich(
            users=[
                {"email": "owner@example.com", "password": "ownerchosen",
                 "isAdmin": True, "storageLabel": "admin"},
                {"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                 "isAdmin": True},
            ],
            owner={"email": "owner@example.com"},
        )
        # Pre-set oauth to the desired state so nothing needs changing.
        backend.system_config["oauth"].update({
            "enabled": True, "issuerUrl": "https://idp.shard.example",
            "clientId": "cid", "clientSecret": "csecret",
            "autoRegister": False, "autoLaunch": True,
        })
        self.wire(backend)
        sidecar.reconcile()
        writes = [c for c in backend.calls if c[0] in ("POST", "PUT", "DELETE")
                  and not c[1].endswith("/api/auth/login")]
        self.assertEqual(writes, [], f"converged shard should write nothing, got {writes}")

    def test_null_owner_email_leaves_existing_account_unchanged(self):
        backend = FakeImmich(
            users=[
                {"email": "owner@example.com", "password": "ownerchosen",
                 "isAdmin": True, "storageLabel": "admin"},
                {"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                 "isAdmin": True},
            ],
            owner={"email": None},
        )
        self.wire(backend)
        sidecar.reconcile()
        email_puts = [c for c in backend.calls
                      if c[0] == "PUT" and "/api/admin/users/" in c[1] and c[2] and "email" in c[2]]
        self.assertEqual(email_puts, [])
        self.assertEqual(non_system(backend)[0]["email"], "owner@example.com")

    def test_multi_user_shard_skips_owner_reconcile(self):
        backend = FakeImmich(
            users=[
                {"email": "a@example.com", "password": "pw", "isAdmin": True, "storageLabel": "admin"},
                {"email": "b@example.com", "password": "pw", "isAdmin": False},
                {"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                 "isAdmin": True},
            ],
            owner={"email": "owner@example.com"},
        )
        self.wire(backend)
        sidecar.reconcile()
        user_puts = [c for c in backend.calls if c[0] == "PUT" and "/api/admin/users/" in c[1]]
        self.assertEqual(user_puts, [], "must not guess which of several users is the owner")

    # --- oauth config ------------------------------------------------------

    def test_oauth_not_touched_when_client_unconfigured(self):
        backend = FakeImmich(
            users=[{"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                    "isAdmin": True}],
            owner={"email": None},
        )
        self.wire(backend, oidc=False)
        self.patch("OIDC_ISSUER", "")
        self.patch("OIDC_CLIENT_ID", "")
        self.patch("OIDC_CLIENT_SECRET", "")
        sidecar.reconcile()
        self.assertEqual(oauth(backend)["enabled"], False)
        config_puts = [c for c in backend.calls if c[0] == "PUT" and c[1].endswith("/api/system-config")]
        self.assertEqual(config_puts, [])

    def test_oauth_put_preserves_other_sections(self):
        backend = FakeImmich(
            users=[{"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                    "isAdmin": True}],
            owner={"email": None},
        )
        self.wire(backend)
        sidecar.reconcile()
        self.assertEqual(backend.system_config["ffmpeg"], {"crf": 23})
        self.assertEqual(backend.system_config["oauth"]["clientId"], "cid")

    def test_oauth_not_rewritten_when_already_correct(self):
        backend = FakeImmich(
            users=[{"email": "freeshard-system@system.freeshard.net", "password": "syssecret",
                    "isAdmin": True}],
            owner={"email": None},
        )
        backend.system_config["oauth"].update({
            "enabled": True, "issuerUrl": "https://idp.shard.example",
            "clientId": "cid", "clientSecret": "csecret",
            "autoRegister": False, "autoLaunch": True,
        })
        self.wire(backend)
        sidecar.reconcile()
        config_puts = [c for c in backend.calls if c[0] == "PUT" and c[1].endswith("/api/system-config")]
        self.assertEqual(config_puts, [])

    # --- failure handling --------------------------------------------------

    def test_transport_error_propagates_for_retry(self):
        def boom(*a, **k):
            raise urllib.error.URLError("connection refused")
        self.patch("_api", boom)
        self.patch("SYSTEM_PASSWORD", "syssecret")
        with self.assertRaises(urllib.error.URLError):
            sidecar.reconcile()

    def test_system_created_but_unauthenticatable_raises(self):
        backend = FakeImmich(users=[], owner={"email": "owner@example.com"},
                             break_system_create=False)
        # Fresh install path uses admin-sign-up, which stores the real pw, so
        # break the subsequent login by mismatching the password instead.
        self.wire(backend, system_pw="syssecret")
        orig = backend.api

        def api(method, url, headers=None, payload=None):
            if url.endswith("/api/auth/admin-sign-up") and payload is not None:
                payload = {**payload, "password": "different"}
            return orig(method, url, headers, payload)
        self.patch("_api", api)
        with self.assertRaises(RuntimeError):
            sidecar.reconcile()

    def test_non_json_200_is_raised_as_runtimeerror(self):
        class FakeResp:
            status = 200
            def read(self):
                return b"<html>not json</html>"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        with unittest.mock.patch("urllib.request.urlopen", return_value=FakeResp()):
            with self.assertRaises(RuntimeError):
                sidecar._api("GET", "http://x/internal/owner")

    def test_main_refuses_without_system_password(self):
        self.patch("SYSTEM_PASSWORD", "")
        self.assertEqual(sidecar.main(), 1)


if __name__ == "__main__":
    unittest.main()
