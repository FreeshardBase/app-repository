from update.update_lib import github_releases, semver_parse


def check(current_version: str) -> dict:
    # nextcloud/server maintains several majors at once and cuts them in batches,
    # so the newest-first release list is not in version order. Pick the highest
    # stable semver tag rather than the first one.
    best = None
    best_version = None
    for release in github_releases("nextcloud/server"):
        if release.get("prerelease"):
            continue
        version = semver_parse(release["tag_name"])
        if version is None:
            continue
        if best_version is None or version > best_version:
            best_version, best = version, release
    if best is None:
        raise ValueError("no stable semver release in nextcloud/server")
    return {
        "latest_version": best["tag_name"].lstrip("v"),
        "release_notes_url": best["html_url"],
        "release_body": best.get("body") or "",
        "upstream_compose_url": None,
    }
