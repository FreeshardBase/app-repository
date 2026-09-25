from update.update_lib import latest_github_release


def check(current_version: str) -> dict:
    # Rybbit tags image and GitHub release identically (vX.Y.Z), and its
    # releases are not flagged prerelease, so the release feed is the source
    # of truth. filter drops any rc/beta tags.
    release = latest_github_release(
        "rybbit-io/rybbit",
        filter_regex=r"^v\d+\.\d+\.\d+$",
    )
    return {
        "latest_version": release["tag_name"],
        "release_notes_url": release["html_url"],
        "release_body": release["body"],
        "upstream_compose_url": "https://raw.githubusercontent.com/rybbit-io/rybbit/master/docker-compose.yml",
    }
