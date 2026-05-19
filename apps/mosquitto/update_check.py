from update.update_lib import latest_dockerhub_tag


def check(current_version: str) -> dict:
    # The Freeshard image is a private build at portalapps.azurecr.io but is based on
    # upstream eclipse-mosquitto, which publishes X.Y.Z tags on Docker Hub.
    latest = latest_dockerhub_tag("eclipse-mosquitto", filter_regex=r"^\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": "https://github.com/eclipse/mosquitto/blob/master/ChangeLog.txt",
        "release_body": None,
        "upstream_compose_url": None,
    }
