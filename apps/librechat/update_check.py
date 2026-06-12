from update.update_lib import latest_ghcr_tag, github_release_body


def check(current_version: str) -> dict:
    # LibreChat flags every GitHub release as a prerelease, so
    # latest_github_release() never matches. Track the ghcr image tags
    # directly instead, filtering to stable vX.Y.Z (drops rc/dev/latest).
    version = latest_ghcr_tag(
        "danny-avila/librechat",
        filter_regex=r"^v\d+\.\d+\.\d+$",
    )
    return {
        "latest_version": version,
        "release_notes_url": f"https://github.com/danny-avila/LibreChat/releases/tag/{version}",
        "release_body": github_release_body("danny-avila/LibreChat", version) or "",
        "upstream_compose_url": None,
    }
