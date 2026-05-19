from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # photoprism tags releases with 6-digit date stamps (YYMMDD), e.g. 230615.
    latest = latest_dockerhub_tag("photoprism/photoprism", filter_regex=r"^\d{6}$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://docs.photoprism.app/release-notes/",
        "release_body": None,
        "upstream_compose_url": None,
    }
