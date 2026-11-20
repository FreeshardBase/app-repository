from update.update_lib import latest_dockerhub_tag

# excalidraw's own three images (frontend/room/storage) are digest-pinned and
# opted out in update_check.py — see the OptOut reason there. The nginx
# reverse proxy that stitches them together is ours, not upstream's, pinned
# with a plain tag, and update_check.py never sees it at all.
SUPPORT_IMAGES = [
    {
        "service": "excalidraw",
        "image": "nginx",
        "latest": lambda: latest_dockerhub_tag("nginx", filter_regex=r"^\d+\.\d+\.\d+-alpine$"),
    },
]
