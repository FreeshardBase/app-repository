#!/usr/bin/env python3
"""Smoke-test an app update bundle on a fresh trial shard.

Assigns a trial shard from the controller, pairs with it, removes the apps that
come pre-installed, then installs every app in the bundle and opens it once to
see whether it actually serves a response.

The per-app timeout applies to each phase separately: an app may take up to
--timeout to install, and up to --timeout again to answer its first request.
Both durations land in the summary table, which is what the timeout should be
tuned from once a few runs have produced numbers.

Stdlib only, like the rest of update/.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import mimetypes
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Optional

DEFAULT_CONTROLLER = "https://controller.freeshard.net"
TERMINAL_NAME = "smoke-test"
USER_AGENT = "freeshard-app-smoke-test"

# Statuses an app can be parked in once installation finished. An app is not
# started by installing it — it starts on the first request.
INSTALL_DONE = {"stopped", "running", "paused"}

log = logging.getLogger("smoke_test")


@dataclass
class AppResult:
    name: str
    install_seconds: Optional[float] = None
    start_seconds: Optional[float] = None
    http_status: Optional[int] = None
    outcome: str = "not reached"
    detail: str = ""
    observed: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.outcome == "PASS"


class Client:
    """Minimal HTTP client with a cookie jar, so the terminal JWT sticks."""

    def __init__(self, timeout: int = 60):
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes = None,
        headers: dict = None,
        timeout: int = None,
    ) -> tuple[int, bytes]:
        """Return (status, body). Never raises on an HTTP error status."""
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", USER_AGENT)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def json_request(self, method: str, url: str, payload=None) -> tuple[int, object]:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        status, body = self.request(method, url, data=data, headers=headers)
        try:
            return status, json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return status, body


def _multipart_body(field_name: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    buffer = io.BytesIO()
    buffer.write(f"--{boundary}\r\n".encode())
    buffer.write(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
    )
    buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode())
    buffer.write(content)
    buffer.write(f"\r\n--{boundary}--\r\n".encode())
    return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"


def assign_trial_shard(client: Client, controller: str) -> dict:
    log.info("requesting a trial shard from %s", controller)
    status, body = client.json_request(
        "POST", f"{controller}/api/shards/assign_trial", payload={}
    )
    if status == 503:
        sys.exit(
            "no standby shard available — the pool is empty, try again once the "
            "controller has prepared one"
        )
    if status not in (200, 201):
        sys.exit(f"could not assign a trial shard: HTTP {status}: {body}")
    return body


def pair(client: Client, domain: str, code: str) -> None:
    query = urllib.parse.urlencode({"code": code})
    status, body = client.json_request(
        "POST",
        f"https://{domain}/core/public/pair/terminal?{query}",
        payload={"name": TERMINAL_NAME},
    )
    if status != 201:
        sys.exit(f"pairing failed: HTTP {status}: {body}")
    if not any(cookie.name == "authorization" for cookie in client.jar):
        sys.exit("pairing returned no authorization cookie")
    log.info("paired as terminal %r", TERMINAL_NAME)


def list_apps(client: Client, domain: str) -> list[dict]:
    status, body = client.json_request("GET", f"https://{domain}/core/protected/apps")
    if status != 200:
        raise RuntimeError(f"listing apps failed: HTTP {status}: {body}")
    return body


def app_status(client: Client, domain: str, name: str) -> tuple[str, str]:
    status, body = client.json_request(
        "GET", f"https://{domain}/core/protected/apps/{name}"
    )
    if status == 404:
        return "absent", ""
    if status != 200:
        raise RuntimeError(f"reading app {name} failed: HTTP {status}: {body}")
    return body.get("status", "unknown"), body.get("status_message") or ""


def remove_preinstalled_apps(
    client: Client, domain: str, timeout: int, poll_interval: float
) -> None:
    """A fresh shard ships with initial_apps installed. They collide with the
    bundle by name and occupy disk the bundle needs, so they go first."""
    preinstalled = [app["name"] for app in list_apps(client, domain)]
    if not preinstalled:
        log.info("no pre-installed apps to remove")
        return

    log.info("removing %d pre-installed apps: %s", len(preinstalled), ", ".join(preinstalled))
    started = time.monotonic()
    for name in preinstalled:
        status, body = client.json_request(
            "DELETE", f"https://{domain}/core/protected/apps/{name}"
        )
        if status not in (204, 404):
            sys.exit(f"could not uninstall pre-installed app {name}: HTTP {status}: {body}")

    deadline = started + timeout
    while time.monotonic() < deadline:
        remaining = [app["name"] for app in list_apps(client, domain)]
        if not remaining:
            log.info("pre-installed apps removed in %ds", round(time.monotonic() - started))
            return
        time.sleep(poll_interval)
    sys.exit(f"pre-installed apps still present after {timeout}s: {remaining}")


def install_app(client: Client, domain: str, name: str, zip_bytes: bytes) -> None:
    data, content_type = _multipart_body("file", f"{name}.zip", zip_bytes)
    status, body = client.request(
        "POST",
        f"https://{domain}/core/protected/apps",
        data=data,
        headers={"Content-Type": content_type},
        timeout=300,
    )
    if status != 201:
        raise RuntimeError(f"upload rejected: HTTP {status}: {body[:300]!r}")


def wait_for_install(
    client: Client, domain: str, name: str, timeout: int, poll_interval: float
) -> tuple[str, str]:
    """Block until the app leaves the installing states. Returns (status, message)."""
    deadline = time.monotonic() + timeout
    last_logged = ""
    while time.monotonic() < deadline:
        status, message = app_status(client, domain, name)
        if status != last_logged:
            log.debug("%s: install status %s", name, status)
            last_logged = status
        if status == "error":
            return status, message
        if status in INSTALL_DONE:
            return status, message
        time.sleep(poll_interval)
    return "timeout", f"still {last_logged or 'unknown'} after {timeout}s"


def open_app(
    client: Client,
    domain: str,
    name: str,
    timeout: int,
    poll_interval: float,
    result: AppResult,
    prefix: str = "",
) -> None:
    """Request the app until it answers, or the budget runs out.

    Three responses are expected while an app boots and none of them means the
    app is broken:

    - 502/503 with the core's splash page, served while the container starts.
    - 404, which means the app currently has no Traefik router: it is still
      queued, in ERROR, or the shared dynamic config was mid-rewrite. Only a
      status of ERROR from the API makes that permanent, so the status is what
      decides.
    - a connection error while Traefik reloads.

    The splash always carries the upstream's error status, never 200, so a 200
    can only come from the app itself.
    """
    url = f"https://{name}.{domain}/"
    prefix = prefix or name
    log.info("%s: opening %s", prefix, url)
    started = time.monotonic()
    deadline = started + timeout
    seen: set[str] = set()

    while time.monotonic() < deadline:
        try:
            status, _ = client.request("GET", url, timeout=30)
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as e:
            observation = f"connection error ({type(e).__name__})"
            status = None
        else:
            observation = f"HTTP {status}"

        if observation not in seen:
            seen.add(observation)
            result.observed.append(observation)
            log.info("%s: %s", prefix, observation)

        if status is not None and 200 <= status < 400:
            result.http_status = status
            result.start_seconds = time.monotonic() - started
            result.outcome = "PASS"
            log.info(
                "%s: answered %s after %ds", prefix, status, round(result.start_seconds)
            )
            return

        if status in (401, 403):
            result.outcome = "FAIL"
            result.http_status = status
            result.detail = (
                f"HTTP {status} — the terminal cookie did not authenticate against the "
                "app; retrying cannot fix that"
            )
            return

        if status == 404:
            current, message = app_status(client, domain, name)
            if current == "error":
                result.outcome = "FAIL"
                result.detail = f"app in error state: {message or 'no message'}"
                result.http_status = status
                return

        time.sleep(poll_interval)

    current, message = app_status(client, domain, name)
    result.outcome = "FAIL"
    result.http_status = status
    result.detail = (
        f"no response within {timeout}s (last: {', '.join(result.observed) or 'nothing'}; "
        f"app status {current}{': ' + message if message else ''})"
    )


def uninstall_app(client: Client, domain: str, name: str) -> None:
    status, body = client.json_request(
        "DELETE", f"https://{domain}/core/protected/apps/{name}"
    )
    if status not in (204, 404):
        log.warning("could not uninstall %s: HTTP %s: %s", name, status, body)


def read_bundle(source: str) -> dict[str, bytes]:
    """Return {app_name: zip bytes} from updated_apps.zip, local path or URL."""
    if source.startswith(("http://", "https://")):
        log.info("downloading bundle from %s", source)
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read()
    else:
        raw = Path(source).read_bytes()

    apps: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        for entry in bundle.namelist():
            if not entry.endswith(".zip"):
                continue
            apps[Path(entry).stem] = bundle.read(entry)
    if not apps:
        sys.exit(f"no app zips found inside {source}")
    return dict(sorted(apps.items()))


def print_summary(results: list[AppResult], shard: dict, keep_installed: bool) -> None:
    name_width = max((len(r.name) for r in results), default=4) + 2
    lines = [
        "",
        "=" * (name_width + 40),
        f"{'app'.ljust(name_width)}{'install':>9}{'start':>9}  result",
        "-" * (name_width + 40),
    ]
    for r in results:
        install = f"{round(r.install_seconds)}s" if r.install_seconds is not None else "-"
        start = f"{round(r.start_seconds)}s" if r.start_seconds is not None else "-"
        lines.append(f"{r.name.ljust(name_width)}{install:>9}{start:>9}  {r.outcome}")
        if r.detail:
            lines.append(f"{' ' * name_width}{' ' * 18}  {r.detail}")
    lines.append("-" * (name_width + 40))

    passed = sum(1 for r in results if r.passed)
    lines.append(f"{passed}/{len(results)} apps started")
    lines.append(f"shard hash-id: {shard['hash_id']}")
    lines.append(f"shard domain:  {shard['domain']}")
    if keep_installed:
        lines.append("apps left installed; the shard deletes itself 24h after assignment")
    else:
        lines.append("apps uninstalled; the shard deletes itself 24h after assignment")
    lines.append("=" * (name_width + 40))
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(
        description="Smoke-test an app update bundle on a fresh trial shard.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "bundle", help="path or URL of updated_apps.zip produced by the preview job"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="per-app budget in seconds, applied to installing and to starting separately",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="seconds between polls; keep below 5 so an app under test is not "
        "demoted by the memory-pressure tier while it boots",
    )
    parser.add_argument(
        "--keep-installed",
        action="store_true",
        help="do not uninstall an app after it passes, so the run doubles as a "
        "memory-pressure test (only meaningful where apps.lifecycle.pause_enabled is on)",
    )
    parser.add_argument("--controller", default=DEFAULT_CONTROLLER)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    apps = read_bundle(args.bundle)
    log.info("bundle contains %d apps: %s", len(apps), ", ".join(apps))

    client = Client()
    shard = assign_trial_shard(client, args.controller)
    domain = shard["domain"]
    log.info("shard hash-id: %s", shard["hash_id"])
    log.info("shard domain:  %s", domain)

    pair(client, domain, shard["code"])
    remove_preinstalled_apps(client, domain, args.timeout, args.poll_interval)

    results: list[AppResult] = []
    run_started = time.monotonic()
    for index, (name, zip_bytes) in enumerate(apps.items(), start=1):
        result = AppResult(name=name)
        results.append(result)
        prefix = f"[{index}/{len(apps)}] {name}"
        log.info("%s: installing (%.1f MiB)", prefix, len(zip_bytes) / 1024 / 1024)

        install_started = time.monotonic()
        try:
            install_app(client, domain, name, zip_bytes)
        except RuntimeError as e:
            result.outcome = "FAIL"
            result.detail = str(e)
            log.error("%s: %s", prefix, e)
            continue

        status, message = wait_for_install(
            client, domain, name, args.timeout, args.poll_interval
        )
        result.install_seconds = time.monotonic() - install_started
        if status in ("error", "timeout"):
            result.outcome = "FAIL"
            result.detail = f"install {status}: {message}" if message else f"install {status}"
            log.error("%s: %s", prefix, result.detail)
            continue
        log.info(
            "%s: installed in %ds, status %s",
            prefix,
            round(result.install_seconds),
            status,
        )

        open_app(
            client, domain, name, args.timeout, args.poll_interval, result, prefix
        )
        if result.outcome != "PASS":
            log.error("%s: %s", prefix, result.detail)

        if not args.keep_installed:
            log.info("%s: uninstalling", prefix)
            uninstall_app(client, domain, name)

    log.info("run finished in %ds", round(time.monotonic() - run_started))
    print_summary(results, shard, args.keep_installed)
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
