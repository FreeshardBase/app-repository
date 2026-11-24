from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("TriliumNext/Trilium")
    return {
        "latest_version": rel["tag_name"],
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        # Upstream renamed the image once already (notes -> trilium) — track it.
        "upstream_compose_url": "https://raw.githubusercontent.com/TriliumNext/Trilium/{version}/docker-compose.yml",
    }
