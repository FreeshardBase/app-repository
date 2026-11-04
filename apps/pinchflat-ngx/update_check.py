from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("TheBadFella/Pinchflat-NGX", filter_regex=r"^\d{4}\.\d+\.\d+$")
    return {
        "latest_version": rel["tag_name"],
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        "upstream_compose_url": None,
    }
