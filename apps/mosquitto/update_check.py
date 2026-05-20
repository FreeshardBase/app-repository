from update.update_lib import OptOut


def check(current_version: str) -> dict:
    # Image is a private build at portalapps.azurecr.io; not auto-updatable.
    # Bumps must be done manually after rebuilding the image.
    raise OptOut("self-built image, manual updates only")
