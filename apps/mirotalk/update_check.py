from update.update_lib import OptOut


def check(current_version: str) -> dict:
    # Upstream cuts no GitHub releases or git tags and publishes a single mutable
    # Docker tag (mirotalk/p2p:latest), so there is no version string to detect.
    # We pin the digest instead; `update.py apply` only string-replaces the version
    # across the app's files and would leave the digest untouched.
    raise OptOut(
        "upstream publishes only the mutable tag mirotalk/p2p:latest, no releases or git tags; "
        "image is digest-pinned, so bump manually: re-resolve the :latest digest and read the "
        "version from the image's /src/package.json"
    )
