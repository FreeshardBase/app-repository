from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("Freika/dawarich")
    return {
        "latest_version": rel["tag_name"],
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        "upstream_compose_url": "https://raw.githubusercontent.com/Freika/dawarich/{version}/docker/docker-compose.yml",
    }
