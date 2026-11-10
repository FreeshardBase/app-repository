#!/usr/bin/env python3
"""Template / reference sidecar.

This is not a real sidecar for any app. It exists only to:

  1. prove the build/publish pipeline in .github/workflows/sidecars.yml
     builds and pushes a real image end-to-end, and
  2. give the author of a real per-app sidecar (see agents.md's "Sidecar Containers" section
     for the full contract) a minimal skeleton that already follows the
     GET -> compare -> PATCH-only-on-mismatch idempotency contract and the
     three-outcome exit/log contract.

A real sidecar replaces get_current_state()/apply_patch() with actual calls
into its app's API, using stdlib only (urllib.request, json) - no pip deps,
per the contract doc.
"""
import logging
import sys
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("sidecar-template")

# Stand-in for "the value the app should have". A real sidecar computes this
# from its own config/environment (e.g. the shard owner's verified email).
DESIRED_VALUE = "configured"


def get_current_state() -> str:
    """Stand-in for a GET against the target app's own API.

    A real sidecar does e.g.:
        req = urllib.request.Request(f"{base_url}/api/admin")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)["email"]
    """
    return DESIRED_VALUE


def apply_patch(desired: str) -> None:
    """Stand-in for the PATCH that fixes a mismatch.

    A real sidecar does e.g.:
        body = json.dumps({"email": desired}).encode()
        req = urllib.request.Request(url, data=body, method="PATCH",
                                      headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    """
    log.info("applied change: set value to %r", desired)


def main() -> int:
    try:
        current = get_current_state()
    except (urllib.error.URLError, OSError) as exc:
        log.error("could not reach target app: %s", exc)
        return 1

    if current == DESIRED_VALUE:
        log.info("nothing to do: already %r", current)
        return 0

    try:
        apply_patch(DESIRED_VALUE)
    except (urllib.error.URLError, OSError) as exc:
        log.error("patch failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
