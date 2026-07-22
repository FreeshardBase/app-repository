from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    latest = latest_dockerhub_tag("sharelatex/sharelatex", filter_regex=r"^\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/overleaf/overleaf/blob/main/CHANGELOG.md",
        "release_body": None,
        "upstream_compose_url": None,
    }
