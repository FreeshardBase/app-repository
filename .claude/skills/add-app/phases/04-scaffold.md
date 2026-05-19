# Phase 4 — Scaffold

Inputs (in `./.add-app-scratch/`):
- `proposed_app_meta.json`, `proposed_docker-compose.yml.template`, `research.json`, `research_notes.md`

Outputs:
- `apps/<name>/app_meta.json`
- `apps/<name>/docker-compose.yml.template`
- `apps/<name>/update_check.py`
- `apps/<name>/icon.svg` or `icon.png` (or none)
- Modified `update.py` if tag-strip rule needed

## Steps

1. **Scaffold from template.** Run `just new-app <name>`. This copies `inactive_apps/template/` to `apps/<name>/` and substitutes `<<name>>`.

2. **Overwrite drafts.** Replace the scaffolded `apps/<name>/app_meta.json` with `proposed_app_meta.json`. Replace `apps/<name>/docker-compose.yml.template` with the proposed compose.

3. **Write `update_check.py`.** Create `apps/<name>/update_check.py` that registers the app with the `/update-apps` orchestrator. Pick the helper that matches the image registry (all helpers live in `update/update_lib.py`):

   - GitHub release (most common): import `latest_github_release`.
   - Docker Hub: import `latest_dockerhub_tag`.
   - ghcr.io: import `latest_ghcr_tag`.
   - lscr.io: import `latest_lscr_tag`.

   The `check(current_version: str) -> dict` function must return `{latest_version, release_notes_url, release_body, upstream_compose_url}`.

   If no clean tag pattern is available for the chosen image, write a stub instead:

   ```python
   def check(current_version: str) -> dict:
       raise NotImplementedError("update_check.py for <name> not yet implemented")
   ```

   The orchestrator surfaces `NotImplementedError` as `error` status; the user can fix it later.

4. **Icon cascade.** Try in order; first success wins. Do not block on failure (proceed without icon).
   a. `curl -fsSL <upstream_repo>/raw/HEAD/logo.svg` (also try `icon.svg`, `assets/logo.svg`, `docs/logo.svg`)
   b. Fetch `<homepage>/favicon.ico` and inspect `<link rel="icon">` tags from `<homepage>/`. If the linked icon is SVG, download it. PNG is acceptable too.
   c. `<homepage>/apple-touch-icon.png`

   If something was fetched, save as `apps/<name>/icon.svg` (or `icon.png` if PNG), overwriting the scaffold's placeholder. Update `apps/<name>/app_meta.json`'s `icon` field accordingly. If nothing found, leave whatever the scaffold provided and add a note to `research_notes.md`: "Icon missing — please add manually."

5. **update.py entry.** If `research.json.tag_strip_v_needed == true`, open `update.py`, find the `adapt_version_string` function, and add `<name>` to the list of apps that strip the `v` prefix. Match surrounding style. If a different tag transformation is needed (suffix strip, prefix add), insert a custom branch and document the rule in `decisions.md`.

6. **Build store data / zip.** Run `just build-store-data` (fallback: `python3 -m build_store_data` if `just` is unavailable). This regenerates `apps/<name>/<name>.zip` and refreshes `apps/store_metadata.json`. Both are gitignored but the zip is uploaded as a PR artifact in phase 5. If the build fails, stop and surface the error — do not push a half-built zip.

7. **Hand off.** Continue to `phases/05-pr.md`.
