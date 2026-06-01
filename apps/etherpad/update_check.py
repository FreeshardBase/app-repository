from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("ether/etherpad-lite", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": rel["tag_name"].lstrip("v"),
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        # Pins postgres independently of the etherpad version — track it.
        "upstream_compose_url": "https://raw.githubusercontent.com/ether/etherpad-lite/v{version}/docker-compose.yml",
    }
