from update.update_lib import github_release_body, latest_dockerhub_tag


def check(current_version: str) -> dict:
    # We run the stock upstream image filebrowser/filebrowser, which publishes vX.Y.Z
    # tags on Docker Hub. Upstream announced the project is archived on 2026-09-01;
    # after that there will be no further releases and no security fixes.
    latest = latest_dockerhub_tag("filebrowser/filebrowser", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": latest,
        "release_notes_url": f"https://github.com/filebrowser/filebrowser/releases/tag/{latest}",
        "release_body": github_release_body("filebrowser/filebrowser", latest),
        "upstream_compose_url": None,
    }
