# Phase 3 — Proposal

Inputs (in `./.add-app-scratch/`):
- `research.json`, `research_notes.md`

Outputs (in `./.add-app-scratch/`):
- `proposed_app_meta.json`
- `proposed_docker-compose.yml.template`
- `decisions.md` — rationale for access mode, volumes, lifecycle, telemetry

## Steps

1. **Read inputs.** Parse `research.json`. Read `research_notes.md` as plain text for nuanced decisions.

2. **Decide access mode.**
   - Default: `private` with the standard X-Ptl-Client-* headers from the template.
   - If `research_notes.md` documents auth-proxy support: use `private` with auth-proxy headers. Pick the username header env var from notes and add it to the compose template's environment block. Add `X-Ptl-User: admin` to the `paths[""].headers`.
   - If notes say the app handles its own auth and is intended for public sharing (e.g., ghost, immich): use `public`.

3. **Decide shared volumes.** Inspect notes for category hints. Map:
   - Music app → `{{ fs.shared }}/music`
   - Photos app → `{{ fs.shared }}/pictures`
   - Documents app → `{{ fs.shared }}/documents`
   - Media (general) → `{{ fs.shared }}/media`
   - No category → app-only, use `{{ fs.app_data }}/data`.

4. **Decide minimum_portal_size.** Map `resource_class_estimate`:
   - `xs` → omit the field (default)
   - `s` → `"minimum_portal_size": "s"`
   - `l` → `"minimum_portal_size": "l"`

5. **Decide lifecycle.**
   - IoT / messaging / always-listening (mqtt, node-red) → `always_on: true`
   - Background jobs / heavy startup → `idle_time_for_shutdown: 3600`
   - Default web app → `idle_time_for_shutdown: 60`

6. **Decide telemetry opt-out.** Read notes for env vars; include each in the compose template `environment:` block.

7. **Draft `proposed_app_meta.json`.** Use the schema in the digest. Required fields filled from `research.json`. `pretty_name` = titlecased name unless notes specify otherwise. `upstream_repo` set from research. `homepage` set if present. `store_info.description_short` from research; `description_long` from notes (parse paragraphs).

8. **Draft `proposed_docker-compose.yml.template`.** Use the patterns from the digest:
   - Single-container apps → minimal template
   - Multi-container apps (Postgres, Redis, etc.) → multi-network template with internal private network
   - Always include `BASE_URL=https://<name>.{{ portal.domain }}` if the app uses BASE_URL or similar
   - Pin image tag to `tag_latest`

9. **Write `decisions.md`.** Short rationale per decision (access mode, shared volume, lifecycle, telemetry, multi-container choice). Used later by PR body.

10. **Ambiguity gate.** If `research.json` has non-empty `ambiguity[]`, present a checkpoint to the user:
    - Show drafted files.
    - List each ambiguity topic with options and the subagent's recommendation.
    - User chooses per topic, edits drafts, or rejects.
    - Reject → hard exit code `reject`. Follow the "Blocked-app documentation" procedure in `reference/exit-criteria.md`: write `blocked_apps/<name>.md`, commit, push, open a non-draft documentation-only PR. Leave the worktree in place.

11. **Hand off.** Continue to `phases/04-scaffold.md`.
