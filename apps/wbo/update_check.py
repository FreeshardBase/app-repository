from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    latest = latest_dockerhub_tag("lovasoa/wbo", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/lovasoa/whitebophir/releases",
        "release_body": None,
        "upstream_compose_url": None,
    }
