from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # Template uses ghost:4-alpine (major-pinned mutable tag).
    # Track strict X.Y.Z-alpine tags so updates surface the real version.
    latest = latest_dockerhub_tag("ghost", filter_regex=r"^\d+\.\d+\.\d+-alpine$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://ghost.org/changelog/",
        "release_body": None,
        "upstream_compose_url": None,
    }
