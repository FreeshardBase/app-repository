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

UPDATE_DIR = Path(__file__).parent
GITHUB_TOKEN_FILE = UPDATE_DIR / "github_token"


def semver_parse(s):
    """Stub. Overridden in Task 4 with full implementation."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", s) if isinstance(s, str) else None
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


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
