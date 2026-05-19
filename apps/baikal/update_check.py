from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    latest = latest_dockerhub_tag("ckulka/baikal", filter_regex=r"^\d+\.\d+\.\d+-nginx$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/sabre-io/Baikal/releases",
        "release_body": None,
        "upstream_compose_url": None,
    }
