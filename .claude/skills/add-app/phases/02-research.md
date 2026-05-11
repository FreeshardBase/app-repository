# Phase 2 — Research

Inputs: `name` from preflight scratch.

Outputs (in `./.add-app-scratch/`):
- `research.json` — structured findings (parsed by phase 3)
- `research_notes.md` — free-form notes (rendered into PR body verbatim)

## Steps

1. **Dispatch research subagent.** Type: `general-purpose`. Prompt:

   ```
   Research the self-hostable app named "<name>" for inclusion in the
   Freeshard app store.

   READ FIRST (as background, do not re-output):
   - /home/ubuntu/projects/freeshard/app-repository/.claude/skills/add-app/reference/freeshard-digest.md

   INVESTIGATE:
   - Docker Hub, GitHub Container Registry, quay.io for an official
     Docker image. If multiple plausible images exist, pick the most
     official by this priority and list rejected candidates in notes:
       1. Image org matches GitHub org of upstream_repo
       2. Image is linked from upstream README/docs
       3. Docker Hub "official" or "verified publisher" badge
       4. Highest pull count
   - GitHub repository: license file, latest release tag, last release
     date, README.
   - Upstream homepage: pricing page (free self-host tier?), docs for
     auth-proxy support, telemetry opt-out, env vars, shared data
     conventions.
   - Determine the container's listening port from the Dockerfile,
     compose example, or upstream docs.

   RETURN a JSON block then a Notes section.

   JSON schema (omit unknown optional fields entirely; do not invent):
   {
     "name": string,
     "homepage": string,
     "upstream_repo": string,
     "license": string,
     "license_class": "foss" | "source-available" | "proprietary",
     "paid": boolean,
     "image": string,
     "tag_latest": string,
     "github_release_tag_example": string | null,
     "tag_strip_v_needed": boolean,
     "last_release_date": "YYYY-MM-DD" | null,
     "abandoned": boolean,
     "container_port": integer,
     "needs_database": boolean,
     "supporting_services": [string, ...],
     "resource_class_estimate": "xs" | "s" | "l",
     "multi_tenant": boolean,
     "needs_privileged": boolean,
     "needs_gpu": boolean,
     "icon_candidates": [string, ...],
     "description_short": string,
     "ambiguity": [{"topic": string, "options": [string, ...], "recommendation": string}, ...],
     "warnings": [string, ...]
   }

   REQUIRED fields (must be present): name, image, tag_latest,
   license_class, container_port, description_short. If you cannot
   determine a required field, set it to null and add an ambiguity
   entry; do not invent a value.

   Notes section (markdown, after JSON):
   - Auth-proxy support (env vars, header names, quirks)
   - Shared volume hints (e.g., this app stores music — fs.shared/music)
   - Telemetry opt-out env vars
   - Alternative image candidates considered and rejected
   - Deployment quirks, security caveats, federation requirements
   - Long description (paragraphs for store_info.description_long)
   - Screenshots URLs
   ```

2. **Parse.** Extract the fenced JSON block to `research.json`. Extract the Notes section (everything after the JSON block) to `research_notes.md`.

3. **Validate required fields.** If any of `name`, `image`, `tag_latest`, `license_class`, `container_port`, `description_short` is missing or null in `research.json`, re-dispatch the subagent once with the missing fields named. If still missing, hard-exit with code a (treating image-related missing fields) or print findings and stop for others.

4. **Manifest inspect.** Run `docker manifest inspect <image>:<tag>` where `<tag>` is `tag_latest`. If exit code non-zero, hard-exit code a. Print the command output to the user.

5. **Apply hard exits.** Read `reference/exit-criteria.md`. Apply hard exits in order: a (already handled), b (`license_class != "foss"`), f (`paid == true` AND no free self-host tier per notes). On hard exit, print findings, do not commit anything, leave worktree for inspection, stop.

6. **Collect soft warnings.** Append to `research.json`'s `warnings[]` any of: c (privileged/gpu), d (multi-tenant), e (abandoned — compute from `last_release_date`), g (resource_class_estimate == "l").

7. **Hand off.** Continue to `phases/03-proposal.md`.
