#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Smoke-test an app update bundle on a fresh trial shard.

Usage: uv run update/smoke_test.py <updated_apps.zip path or URL>

Assigns a trial shard from the controller, pairs with it, removes the apps that
come pre-installed, then installs every app in the bundle and opens it once to
see whether it actually serves a response.

The per-app timeout applies to each phase separately: an app may take up to
--timeout to install, and up to --timeout again to answer its first request.
Both durations land in the summary table, which is what the timeout should be
tuned from once a few runs have produced numbers.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_CONTROLLER = "https://controller.freeshard.net"
TERMINAL_NAME = "smoke-test"

# Statuses an app can be parked in once installation finished. An app is not
# started by installing it — it starts on the first request.
INSTALL_DONE = {"stopped", "running", "paused"}

# Installing or uninstalling any app rewrites the shared Traefik dynamic config,
# and the core's own routers live in that same file, so a call landing inside the
# rewrite gets Traefik's 404 instead of an answer from the core.
TRANSIENT_STATUS = {404, 500, 502, 503, 504}

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


def core_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 6,
    delay: float = 2.0,
    **kwargs,
) -> httpx.Response:
    """Call the shard core, riding out the window where Traefik has no routers."""
    last: httpx.Response | httpx.HTTPError | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            last = e
        else:
            if response.status_code not in TRANSIENT_STATUS:
                return response
            last = response
        if attempt < attempts:
            log.debug(
                "core %s %s: %s, retrying (%d/%d)",
                method,
                url,
                last.status_code if isinstance(last, httpx.Response) else type(last).__name__,
                attempt,
                attempts,
            )
            time.sleep(delay)
    if isinstance(last, httpx.Response):
        return last
    raise last


def assign_trial_shard(client: httpx.Client, controller: str) -> dict:
    log.info("requesting a trial shard from %s", controller)
    response = client.post(f"{controller}/api/shards/assign_trial", json={})
    if response.status_code == 503:
        sys.exit(
            "no standby shard available — the pool is empty, try again once the "
            "controller has prepared one"
        )
    if response.status_code not in (200, 201):
        sys.exit(
            f"could not assign a trial shard: HTTP {response.status_code}: {response.text}"
        )
    return response.json()


def pair(client: httpx.Client, domain: str, code: str) -> None:
    response = core_request(
        client,
        "POST",
        f"https://{domain}/core/public/pair/terminal",
        params={"code": code},
        json={"name": TERMINAL_NAME},
    )
    if response.status_code != 201:
        sys.exit(f"pairing failed: HTTP {response.status_code}: {response.text}")
    if not client.cookies.get("authorization", domain=f".{domain}"):
        sys.exit("pairing returned no authorization cookie")
    log.info("paired as terminal %r", TERMINAL_NAME)


def list_apps(client: httpx.Client, domain: str) -> list[dict]:
    response = core_request(client, "GET", f"https://{domain}/core/protected/apps")
    response.raise_for_status()
    return response.json()


def app_status(client: httpx.Client, domain: str, name: str) -> tuple[str, str]:
    response = core_request(client, "GET", f"https://{domain}/core/protected/apps/{name}")
    if response.status_code == 404:
        return "absent", ""
    response.raise_for_status()
    body = response.json()
    return body.get("status", "unknown"), body.get("status_message") or ""


def remove_preinstalled_apps(
    client: httpx.Client, domain: str, timeout: int, poll_interval: float
) -> None:
    """A fresh shard ships with initial_apps installed. They collide with the
    bundle by name and occupy disk the bundle needs, so they go first."""
    preinstalled = [app["name"] for app in list_apps(client, domain)]
    if not preinstalled:
        log.info("no pre-installed apps to remove")
        return

    log.info(
        "removing %d pre-installed apps: %s", len(preinstalled), ", ".join(preinstalled)
    )
    started = time.monotonic()
    for name in preinstalled:
        response = core_request(client, "DELETE", f"https://{domain}/core/protected/apps/{name}")
        if response.status_code not in (204, 404):
            sys.exit(
                f"could not uninstall pre-installed app {name}: "
                f"HTTP {response.status_code}: {response.text}"
            )

    deadline = started + timeout
    while time.monotonic() < deadline:
        remaining = [app["name"] for app in list_apps(client, domain)]
        if not remaining:
            log.info(
                "pre-installed apps removed in %ds", round(time.monotonic() - started)
            )
            return
        time.sleep(poll_interval)
    sys.exit(f"pre-installed apps still present after {timeout}s: {remaining}")


def install_app(client: httpx.Client, domain: str, name: str, zip_bytes: bytes) -> None:
    response = core_request(
        client,
        "POST",
        f"https://{domain}/core/protected/apps",
        files={"file": (f"{name}.zip", zip_bytes, "application/zip")},
        timeout=300,
    )
    # 409 means a retried upload landed after the first one had in fact been accepted.
    if response.status_code not in (201, 409):
        raise RuntimeError(
            f"upload rejected: HTTP {response.status_code}: {response.text[:300]}"
        )


def wait_for_install(
    client: httpx.Client, domain: str, name: str, timeout: int, poll_interval: float
) -> tuple[str, str]:
    """Block until the app leaves the installing states. Returns (status, message)."""
    deadline = time.monotonic() + timeout
    last_seen = ""
    while time.monotonic() < deadline:
        status, message = app_status(client, domain, name)
        if status != last_seen:
            log.debug("%s: install status %s", name, status)
            last_seen = status
        if status == "error" or status in INSTALL_DONE:
            return status, message
        time.sleep(poll_interval)
    return "timeout", f"still {last_seen or 'unknown'} after {timeout}s"


def open_app(
    client: httpx.Client,
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
    - a transport error while Traefik reloads.

    The splash always carries the upstream's error status, never 200, so a 2xx
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
            status = client.get(url, timeout=30).status_code
        except httpx.HTTPError as e:
            status = None
            observation = f"transport error ({type(e).__name__})"
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
                f"HTTP {status} — the terminal cookie did not authenticate against "
                "the app; retrying cannot fix that"
            )
            return

        if status == 404:
            current, message = app_status(client, domain, name)
            if current == "error":
                result.outcome = "FAIL"
                result.http_status = status
                result.detail = f"app in error state: {message or 'no message'}"
                return

        time.sleep(poll_interval)

    current, message = app_status(client, domain, name)
    result.outcome = "FAIL"
    result.http_status = status
    result.detail = (
        f"no response within {timeout}s (last: {', '.join(result.observed) or 'nothing'}; "
        f"app status {current}{': ' + message if message else ''})"
    )


def uninstall_app(client: httpx.Client, domain: str, name: str) -> None:
    response = core_request(client, "DELETE", f"https://{domain}/core/protected/apps/{name}")
    if response.status_code not in (204, 404):
        log.warning(
            "could not uninstall %s: HTTP %s: %s",
            name,
            response.status_code,
            response.text,
        )


def read_bundle(source: str) -> dict[str, bytes]:
    """Return {app_name: zip bytes} from updated_apps.zip, local path or URL."""
    if source.startswith(("http://", "https://")):
        log.info("downloading bundle from %s", source)
        raw = httpx.get(source, timeout=300, follow_redirects=True).content
    else:
        raw = Path(source).read_bytes()

    apps: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        for entry in bundle.namelist():
            if entry.endswith(".zip"):
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
        install = (
            f"{round(r.install_seconds)}s" if r.install_seconds is not None else "-"
        )
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
        lines.append(
            "apps left installed; the shard deletes itself 24h after assignment"
        )
    else:
        lines.append("apps uninstalled; the shard deletes itself 24h after assignment")
    lines.append("=" * (name_width + 40))
    print("\n".join(lines))


def run(args: argparse.Namespace) -> int:
    apps = read_bundle(args.bundle)
    log.info("bundle contains %d apps: %s", len(apps), ", ".join(apps))
    results: list[AppResult] = []
    run_started = time.monotonic()

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        shard = assign_trial_shard(client, args.controller)
        domain = shard["domain"]
        log.info("shard hash-id: %s", shard["hash_id"])
        log.info("shard domain:  %s", domain)

        pair(client, domain, shard["code"])
        remove_preinstalled_apps(client, domain, args.timeout, args.poll_interval)

        for index, (name, zip_bytes) in enumerate(apps.items(), start=1):
            result = AppResult(name=name)
            results.append(result)
            prefix = f"[{index}/{len(apps)}] {name}"
            log.info("%s: installing (%.1f MiB)", prefix, len(zip_bytes) / 1024 / 1024)

            install_started = time.monotonic()
            try:
                install_app(client, domain, name, zip_bytes)
            except (RuntimeError, httpx.HTTPError) as e:
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
                result.detail = (
                    f"install {status}: {message}" if message else f"install {status}"
                )
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
    return 0 if all(r.passed for r in results) else 1


def main() -> None:
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
