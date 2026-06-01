from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("paperless-ngx/paperless-ngx", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": rel["tag_name"].lstrip("v"),
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        # Pins postgres + redis independently of the paperless version — track them.
        "upstream_compose_url": "https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/v{version}/docker/compose/docker-compose.postgres.yml",
    }
