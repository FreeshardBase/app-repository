from update.update_lib import latest_dockerhub_tag

# librechat's own image is tracked by update_check.py. mongodb and
# meilisearch are support images pinned directly in the compose template
# and update_check.py never sees either. mongodb (mongo:7.0) floats on
# patch within the 7.0 line already, so there is nothing to check there;
# meilisearch (getmeili/meilisearch:vX.Y.Z) is a full, non-floating pin.
SUPPORT_IMAGES = [
    {
        "service": "librechat-meilisearch",
        "image": "getmeili/meilisearch",
        "latest": lambda: latest_dockerhub_tag(
            "getmeili/meilisearch", filter_regex=r"^v\d+\.\d+\.\d+$"
        ),
        # Meilisearch's own versioning policy allows a MINOR release to
        # require a manual dump/reimport (a DB-incompatible change does not
        # by itself force a MAJOR bump): https://github.com/meilisearch/
        # engine-team/blob/main/resources/versioning-policy.md. "minor is
        # safe to auto-apply" does not hold for this image.
        "always_review_reason": "meilisearch minor releases can require a manual dump, not just major",
    },
]
