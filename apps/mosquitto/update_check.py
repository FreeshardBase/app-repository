import re

from update.update_lib import _http_get_text, latest_dockerhub_tag

# Upstream publishes git tags and Docker images but no GitHub releases, so
# Docker Hub is the authoritative tag source and ChangeLog.txt the release notes.
# Plain `X.Y.Z` tags are the 2.0 line; the 2.1 line is published as
# `2.1.x-alpine` only and is deliberately not matched here.
TAG_RE = r"^\d+\.\d+\.\d+$"
CHANGELOG_RAW = "https://raw.githubusercontent.com/eclipse-mosquitto/mosquitto/v{version}/ChangeLog.txt"
CHANGELOG_HTML = "https://github.com/eclipse-mosquitto/mosquitto/blob/v{version}/ChangeLog.txt"


def _changelog_section(version: str) -> str:
    text = _http_get_text(CHANGELOG_RAW.format(version=version))
    match = re.search(
        rf"^{re.escape(version)} - .*?(?=^\d+\.\d+\.\d+ - )",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(0).strip() if match else ""


def check(current_version: str) -> dict:
    latest = latest_dockerhub_tag("eclipse-mosquitto", filter_regex=TAG_RE)
    return {
        "latest_version": latest,
        "release_notes_url": CHANGELOG_HTML.format(version=latest),
        "release_body": _changelog_section(latest),
    }
