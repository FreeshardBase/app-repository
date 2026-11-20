import re

from update.update_lib import _http_get_json

# SearXNG publishes no GitHub releases and no git tags; the only version
# marker is the Docker Hub tag `YYYY.M.D-<short sha>`. These do not parse as
# semver, so `_pick_latest` cannot order them - ask Docker Hub for the most
# recently pushed tag instead.
TAGS_URL = (
    "https://hub.docker.com/v2/repositories/searxng/searxng/tags"
    "?page_size=100&ordering=last_updated"
)
TAG_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}-[0-9a-f]{9}$")


def check(current_version: str) -> dict:
    data = _http_get_json(TAGS_URL)
    latest = next(t["name"] for t in data["results"] if TAG_RE.match(t["name"]))

    notes_url = "https://github.com/searxng/searxng/commits/master"
    if TAG_RE.match(current_version) and current_version != latest:
        notes_url = (
            "https://github.com/searxng/searxng/compare/"
            f"{current_version.split('-')[1]}...{latest.split('-')[1]}"
        )

    return {
        "latest_version": latest,
        "release_notes_url": notes_url,
        "release_body": None,
        "upstream_compose_url": None,
    }
