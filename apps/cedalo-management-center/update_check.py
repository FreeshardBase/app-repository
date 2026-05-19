from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    latest = latest_dockerhub_tag("cedalo/management-center", filter_regex=r"^\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://hub.docker.com/r/cedalo/management-center/tags",
        "release_body": None,
        "upstream_compose_url": None,
    }
