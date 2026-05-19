from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    rel = latest_github_release("usememos/memos", filter_regex=r"^v\d+\.\d+\.\d+$")
    return {
        "latest_version": rel["tag_name"].lstrip("v"),
        "release_notes_url": rel["html_url"],
        "release_body": rel["body"],
        "upstream_compose_url": None,
    }
