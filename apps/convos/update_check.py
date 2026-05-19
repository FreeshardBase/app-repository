import re

from update.update_lib import _github_headers, _http_get_json


def check(current_version: str) -> dict:
    # Convos has no GitHub releases; track versioned git tags (vX.YY format).
    # The Docker image at ghcr.io/convos-chat/convos is tagged with the same version strings.
    tags = _http_get_json(
        "https://api.github.com/repos/convos-chat/convos/tags?per_page=50",
        headers=_github_headers(),
    )
    pat = re.compile(r"^v\d+\.\d+$")
    matched = [t["name"] for t in tags if pat.match(t["name"])]
    if not matched:
        raise ValueError("no versioned tags found for convos-chat/convos")
    latest = matched[0]  # GH tags API returns newest first
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/convos-chat/convos/blob/main/Changes.md",
        "release_body": None,
        "upstream_compose_url": None,
    }
