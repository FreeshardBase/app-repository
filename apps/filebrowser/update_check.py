from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # The Freeshard image is a private build at portalapps.azurecr.io but tracks upstream
    # filebrowser/filebrowser, which publishes vX.Y.Z tags on Docker Hub.
    latest = latest_dockerhub_tag("filebrowser/filebrowser", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/filebrowser/filebrowser/releases",
        "release_body": None,
        "upstream_compose_url": None,
    }
