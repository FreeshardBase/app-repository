"""Helpers used by per-app update_check.py scripts and the orchestrator."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

USER_AGENT = "freeshard-app-update-checker"
TIMEOUT = 30


class OptOut(Exception):
    """Raised by an app's update_check.py to opt out of auto-update detection.

    Used for apps whose updates must be done manually — self-built images,
    upstreams with unreliable tag schemes, etc. The orchestrator records the
    reason and marks the app as `opt_out` (distinct from `error`).
    """

UPDATE_DIR = Path(__file__).parent
GITHUB_TOKEN_FILE = UPDATE_DIR / "github_token"


def _http_get_json(url: str, headers: Optional[dict] = None) -> dict | list:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, headers: Optional[dict] = None) -> str:
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def _pick_latest(tags: list[str], filter_regex: str,
                 strip_prefix: Optional[str] = None,
                 suffix: Optional[str] = None) -> str:
    """Filter tags by regex, semver-sort, return latest with optional transforms."""
    pat = re.compile(filter_regex)
    matched = [t for t in tags if pat.match(t)]
    if not matched:
        raise ValueError(f"no tags matched {filter_regex!r}")

    def sort_key(t: str):
        s = t
        if strip_prefix and s.startswith(strip_prefix):
            s = s[len(strip_prefix):]
        parsed = semver_parse(s)
        return parsed if parsed else (0, 0, 0)

    matched.sort(key=sort_key, reverse=True)
    latest = matched[0]
    if strip_prefix and latest.startswith(strip_prefix):
        latest = latest[len(strip_prefix):]
    if suffix:
        latest = latest + suffix
    return latest


def latest_dockerhub_tag(image: str, filter_regex: str = r".*",
                          strip_prefix: Optional[str] = None,
                          suffix: Optional[str] = None) -> str:
    """`image` is `org/name` (or `library/name` for official images)."""
    if "/" not in image:
        image = f"library/{image}"
    tags = []
    url = f"https://hub.docker.com/v2/repositories/{image}/tags?page_size=100"
    while url:
        data = _http_get_json(url)
        tags.extend(t["name"] for t in data.get("results", []))
        url = data.get("next")
        if len(tags) > 500:  # safety cap
            break
    return _pick_latest(tags, filter_regex, strip_prefix, suffix)


def latest_ghcr_tag(image: str, filter_regex: str = r".*",
                     strip_prefix: Optional[str] = None,
                     suffix: Optional[str] = None) -> str:
    """`image` is `owner/name`. Uses the GHCR token-less API."""
    token_url = f"https://ghcr.io/token?scope=repository:{image}:pull"
    token = _http_get_json(token_url)["token"]
    list_url = f"https://ghcr.io/v2/{image}/tags/list?n=1000"
    data = _http_get_json(list_url, headers={"Authorization": f"Bearer {token}"})
    return _pick_latest(data.get("tags", []), filter_regex, strip_prefix, suffix)


def latest_lscr_tag(image: str, filter_regex: str = r".*",
                     strip_prefix: Optional[str] = None,
                     suffix: Optional[str] = None) -> str:
    """linuxserver.io ships via ghcr; same protocol."""
    return latest_ghcr_tag(image, filter_regex, strip_prefix, suffix)


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN_FILE.exists():
        token = GITHUB_TOKEN_FILE.read_text().strip()
        headers["Authorization"] = f"token {token}"
    return headers


def github_releases(repo: str) -> list[dict]:
    """`repo` is `owner/name`. Returns list of release dicts, newest first."""
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    return _http_get_json(url, headers=_github_headers())


def latest_github_release(repo: str, filter_regex: Optional[str] = None) -> dict:
    """Returns the first non-prerelease release whose tag matches filter_regex.

    Return shape: {tag_name, body, html_url}.
    """
    pat = re.compile(filter_regex) if filter_regex else None
    for r in github_releases(repo):
        if r.get("prerelease"):
            continue
        if pat and not pat.match(r["tag_name"]):
            continue
        return {"tag_name": r["tag_name"], "body": r.get("body") or "", "html_url": r["html_url"]}
    raise ValueError(f"no matching release in {repo}")


def github_release_body(repo: str, tag: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    try:
        data = _http_get_json(url, headers=_github_headers())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return data.get("body") or ""


def semver_parse(s: str) -> Optional[tuple[int, int, int]]:
    """Parse X.Y.Z, tolerating an optional leading `v`. Returns None if not semver."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def semver_jump(old: str, new: str) -> str:
    """Returns 'patch' | 'minor' | 'major' | 'non_semver'."""
    o = semver_parse(old)
    n = semver_parse(new)
    if not o or not n:
        return "non_semver"
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"


COMPOSE_CACHE_DIR = UPDATE_DIR / "update_info" / "upstream_compose_cache"


def fetch_upstream_compose(app_name: str, version: str, url: str) -> str:
    """Cache-on-disk fetch of an upstream docker-compose file at a given version.

    Cache key is (app, version) — tag content is immutable.
    """
    cache_path = COMPOSE_CACHE_DIR / app_name / f"{version}.yml"
    if cache_path.exists():
        return cache_path.read_text()
    text = _http_get_text(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text)
    return text


_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]+")


def compose_diff(
    old_yaml: str,
    new_yaml: str,
    old_version: str | None = None,
    new_version: str | None = None,
) -> tuple[str, bool]:
    """Unified diff of an upstream docker-compose across two versions.

    `nontrivial` is True iff the diff contains changes beyond the app's own
    version bump — i.e. a *supporting* image tag change (postgres, redis, ...)
    or a structural change. These are the changes the version bumper does NOT
    carry into our template (it only string-replaces the app version), so they
    must force human REVIEW.

    The flag is computed on a normalized comparison: image digests are stripped
    and the app's own version is neutralized (old -> new), so the routine
    main-image bump cancels out and only independent changes remain. The full,
    un-normalized diff text is returned for human review.
    """
    import difflib

    diff_lines = list(difflib.unified_diff(
        old_yaml.splitlines(keepends=False),
        new_yaml.splitlines(keepends=False),
        fromfile="old", tofile="new", lineterm="",
    ))

    def _norm(text: str) -> str:
        text = _DIGEST_RE.sub("", text)
        if old_version and new_version:
            text = text.replace(old_version, new_version)
        return text

    nontrivial = any(
        (line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
        for line in difflib.unified_diff(
            _norm(old_yaml).splitlines(keepends=False),
            _norm(new_yaml).splitlines(keepends=False),
            lineterm="",
        )
    )
    return "\n".join(diff_lines), nontrivial
