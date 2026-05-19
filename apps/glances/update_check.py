from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # Template uses nicolargo/glances:X.Y.Z.W-full (4-part version with -full suffix).
    latest = latest_dockerhub_tag(
        "nicolargo/glances",
        filter_regex=r"^\d+\.\d+\.\d+(\.\d+)?-full$",
    )
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/nicolargo/glances/releases",
        "release_body": None,
        "upstream_compose_url": None,
    }
