from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("kromitgmbh/titra")
    return {
        "latest_version": rel["tag_name"],
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        # Pins mongo independently of the titra version — track it. Tags have no `v` prefix.
        "upstream_compose_url": "https://raw.githubusercontent.com/kromitgmbh/titra/{version}/docker-compose.yml",
    }
