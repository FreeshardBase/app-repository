def check(current_version: str) -> dict:
    # Docker Hub `joplin/server` publishes tags for both stable and prerelease GitHub
    # releases (e.g. 3.7.1 is a prerelease) without exposing the prerelease flag.
    # Tag set is also sparse — many GitHub stable releases never get a Docker tag.
    # Auto-detection is unreliable; bump manually after checking upstream.
    raise NotImplementedError("upstream publishes prereleases as plain Docker tags; manual updates only")
