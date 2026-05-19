from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # joplin/server publishes X.Y.Z semver tags on Docker Hub.
    latest = latest_dockerhub_tag("joplin/server", filter_regex=r"^\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/laurent22/joplin/releases",
        "release_body": None,
        "upstream_compose_url": None,
    }
