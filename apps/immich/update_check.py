from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("immich-app/immich")
    return {
        "latest_version": rel["tag_name"],
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        # Immich pins its postgres (vector extension) image in this compose and
        # bumps it independently of the server version. Tracking it forces REVIEW
        # when the DB image changes — the drift that caused the pgvecto.rs outage.
        "upstream_compose_url": "https://raw.githubusercontent.com/immich-app/immich/{version}/docker/docker-compose.yml",
    }
