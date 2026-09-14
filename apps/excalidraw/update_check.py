from update.update_lib import OptOut


def check(current_version: str) -> dict:
    raise OptOut(
        "excalidraw pins three images by digest (the frontend alswl/excalidraw, "
        "the excalidraw/excalidraw-room collaboration server, and the "
        "alswl/excalidraw-storage-backend), because they publish only mutable "
        "tags. update.py apply only string-replaces app_version, which would bump "
        "the version while leaving the digests stale. Bump by hand: re-resolve the "
        "newest alswl/excalidraw fork tag to its digest, set app_version to that "
        "tag's Excalidraw version, and refresh the room/storage digests as needed."
    )
