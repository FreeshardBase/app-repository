from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("element-hq/element-web", filter_regex=r"^v\d+\.\d+\.\d+")
    latest = rel["tag_name"].split("-")[0]
    return {
        "latest_version": latest,
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        "upstream_compose_url": None,
    }
