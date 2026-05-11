# add-app skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `add-app` skill for app-repository: researches an app, decides Freeshard fit, drafts integration files, opens a PR. Reevaluation mode triggers when the app already exists.

**Architecture:** Markdown-only skill. `SKILL.md` orchestrates. One file per phase under `phases/`. Vendored, age-gated `freeshard-digest.md` reference. Slash command `add-app` thin-wraps the skill. No Python — all logic lives as instructions interpreted by the agent at run time. Worktree isolation per run.

**Tech stack:** Markdown, bash (in instructions), `gh` CLI, `docker manifest inspect`, `git worktree`, subagent dispatch (general-purpose for research and digest refresh).

**Spec:** `docs/superpowers/specs/2026-05-10-add-app-skill-design.md`

---

## File Structure

Files this plan creates or modifies:

| Path | Purpose |
|---|---|
| `.gitignore` | Add `.claude/worktrees/` so worktree contents stay out of commits |
| `.claude/skills/add-app/SKILL.md` | Top-level orchestration: phase dispatch, mode select |
| `.claude/skills/add-app/phases/01-preflight.md` | Name sanitize, digest age check, collision detection |
| `.claude/skills/add-app/phases/02-research.md` | Research subagent prompt + contract, manifest inspect, hard-exit gate |
| `.claude/skills/add-app/phases/03-proposal.md` | Draft `app_meta.json` and `docker-compose.yml.template`, decide access model, ambiguity checkpoint |
| `.claude/skills/add-app/phases/04-scaffold.md` | Worktree, `just new-app`, write files, icon cascade, `update.py` entry |
| `.claude/skills/add-app/phases/05-pr.md` | Commit, `gh pr create`, render PR body |
| `.claude/skills/add-app/phases/reeval.md` | Reevaluation mode flow |
| `.claude/skills/add-app/reference/freeshard-digest.md` | Compact AI-optimized summary of `docs.freeshard.net` |
| `.claude/skills/add-app/reference/digest-meta.json` | `{generated_at, source_urls[]}` for age check |
| `.claude/skills/add-app/reference/exit-criteria.md` | License classification table, hard/soft criteria rules |
| `.claude/skills/add-app/templates/pr-body.md` | PR body template (new-app + reevaluation variants) |
| `.claude/commands/add-app.md` | Slash command, invokes skill with `$1` |

Each phase file is self-contained: the orchestrator reads only `SKILL.md`, then opens each phase file in sequence. Cross-references between phases use named outputs (e.g., phase 2 outputs `research.json` and `research_notes.md` to scratch in the worktree; phase 3 reads them). This keeps SKILL.md small and lets each phase be edited without rereading the others.

---

## Task 1: Add gitignore entry for worktrees

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Edit .gitignore**

Append the line `.claude/worktrees/` to `.gitignore`. Result tail of file:

```
update_info
.claude/worktrees/
```

- [ ] **Step 2: Verify**

Run: `git check-ignore -v .claude/worktrees/add-app-skill`
Expected: prints `.gitignore:N:.claude/worktrees/  .claude/worktrees/add-app-skill`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .claude/worktrees/"
```

---

## Task 2: Skill scaffolding (empty files + dirs)

**Files:**
- Create: `.claude/skills/add-app/SKILL.md` (stub)
- Create: `.claude/skills/add-app/phases/01-preflight.md` (stub)
- Create: `.claude/skills/add-app/phases/02-research.md` (stub)
- Create: `.claude/skills/add-app/phases/03-proposal.md` (stub)
- Create: `.claude/skills/add-app/phases/04-scaffold.md` (stub)
- Create: `.claude/skills/add-app/phases/05-pr.md` (stub)
- Create: `.claude/skills/add-app/phases/reeval.md` (stub)
- Create: `.claude/skills/add-app/reference/exit-criteria.md` (stub)
- Create: `.claude/skills/add-app/reference/freeshard-digest.md` (stub)
- Create: `.claude/skills/add-app/reference/digest-meta.json` (stub `{}`)
- Create: `.claude/skills/add-app/templates/pr-body.md` (stub)
- Create: `.claude/commands/add-app.md` (stub)

- [ ] **Step 1: Create directories and stub files**

```bash
mkdir -p .claude/skills/add-app/phases .claude/skills/add-app/reference .claude/skills/add-app/templates .claude/commands
for f in \
  .claude/skills/add-app/SKILL.md \
  .claude/skills/add-app/phases/01-preflight.md \
  .claude/skills/add-app/phases/02-research.md \
  .claude/skills/add-app/phases/03-proposal.md \
  .claude/skills/add-app/phases/04-scaffold.md \
  .claude/skills/add-app/phases/05-pr.md \
  .claude/skills/add-app/phases/reeval.md \
  .claude/skills/add-app/reference/exit-criteria.md \
  .claude/skills/add-app/reference/freeshard-digest.md \
  .claude/skills/add-app/templates/pr-body.md \
  .claude/commands/add-app.md ; do
  printf "# %s\n\nStub. See plan.\n" "$f" > "$f"
done
echo '{}' > .claude/skills/add-app/reference/digest-meta.json
```

- [ ] **Step 2: Verify**

Run: `find .claude/skills/add-app .claude/commands -type f | sort`
Expected: lists all 11 files above + `digest-meta.json`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app .claude/commands/add-app.md
git commit -m "scaffold: add-app skill skeleton"
```

---

## Task 3: Write reference/exit-criteria.md

**Files:**
- Modify: `.claude/skills/add-app/reference/exit-criteria.md`

This file is read by phase 2 (research) and phase 3 (proposal). It is the single source of truth for hard/soft classification and license mapping. No Python — agent reads it and applies.

- [ ] **Step 1: Write exit-criteria.md**

```markdown
# Exit Criteria

## Hard exits (skill stops, prints findings, no PR)

| Code | Trigger | Detection |
|---|---|---|
| a | No official Docker image | `docker manifest inspect <image>:<tag>` returns non-zero, or research subagent could not locate any image |
| b | Non-FOSS license | `license_class ∈ {source-available, proprietary}` |
| f | Paid / license-key required | `paid == true` AND no documented free self-host tier |

## Soft warnings (render in PR body, do not stop)

| Code | Trigger | Detection |
|---|---|---|
| c | Requires GPU / kernel modules / privileged | `needs_gpu == true` OR `needs_privileged == true` |
| d | Multi-tenant SaaS architecture | `multi_tenant == true` |
| e | Abandoned | `last_release_date` older than 12 months from today |
| g | Heavy idle RAM (>2 GB) | `resource_class_estimate == "l"` |

## Route

| Code | Trigger | Action |
|---|---|---|
| h | Already in `apps/<name>/` or `inactive_apps/<name>/` | Switch to reevaluation mode (see `phases/reeval.md`) |

## License classification

Set `license_class` from upstream LICENSE file / repository metadata:

| Class | Licenses |
|---|---|
| `foss` | MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, GPL-2.0, GPL-3.0, AGPL-3.0, LGPL-*, MPL-2.0, ISC, Unlicense, CC0-1.0 |
| `source-available` | BSL (Business Source License), SSPL, Elastic License v2, Confluent Community License, Redis Source Available License |
| `proprietary` | EULA-only, no source available, "all rights reserved" |

Edge cases (re-licensed projects, dual-licensed, custom): pick the most restrictive class. Document the actual license name in JSON (`license`) and reasoning in notes.
```

- [ ] **Step 2: Verify**

Run: `wc -l .claude/skills/add-app/reference/exit-criteria.md`
Expected: between 30 and 50 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/reference/exit-criteria.md
git commit -m "add-app: write exit-criteria reference"
```

---

## Task 4: Write reference/freeshard-digest.md (compact docs summary)

**Files:**
- Modify: `.claude/skills/add-app/reference/freeshard-digest.md`
- Modify: `.claude/skills/add-app/reference/digest-meta.json`

This digest is what the research subagent and the proposal phase read to understand the Freeshard integration model. Initial content is derived from the existing `agents.md` at the repository root, supplemented by a one-time crawl of `docs.freeshard.net`. Keep it dense: the agent reads it every run.

- [ ] **Step 1: Dispatch a research subagent to compile the digest**

Use the `general-purpose` agent type. Prompt:

```
Build a compact, AI-optimized reference describing the Freeshard app
integration model. Inputs:

1. /home/ubuntu/projects/freeshard/app-repository/agents.md (read in full)
2. https://docs.freeshard.net (crawl the navigation; read the pages
   that describe apps, the app store, access modes, container model,
   template variables, lifecycle, networking, and the manifest schema)

Output: a single markdown document for `reference/freeshard-digest.md`,
under 400 lines, organized in these sections:

- App model (one container or many, ports, networks)
- `app_meta.json` schema (all fields, with concise descriptions and
  allowed values; mirror agents.md)
- `docker-compose.yml.template` rules (network, container_name,
  volumes, restart, image tags, internal networking, shared volumes)
- Template variables (`portal.*`, `fs.*`)
- Access modes (`private`, `public`, `peer`), header templating, auth-proxy
  patterns
- Lifecycle (`always_on`, `idle_time_for_shutdown`) — when to use which
- `minimum_portal_size` classes and when to set them
- Common patterns (auth-proxy header env vars per app family, shared
  data paths, telemetry opt-outs)
- Update flow (upstream_repo, update.py adapt_version_string, when
  image tags differ from GitHub release tags)

Also output a JSON block with the list of source URLs you actually
read (for digest-meta.json).

Return the markdown document, then a fenced JSON block:
{"source_urls": ["https://docs.freeshard.net/...", ...]}
```

- [ ] **Step 2: Save the digest**

Save the returned markdown to `.claude/skills/add-app/reference/freeshard-digest.md`. Replace stub content entirely.

- [ ] **Step 3: Save digest-meta.json**

Write `.claude/skills/add-app/reference/digest-meta.json` with today's date and the source URLs from the subagent. Format:

```json
{
  "generated_at": "YYYY-MM-DD",
  "source_urls": [
    "https://docs.freeshard.net/...",
    "..."
  ]
}
```

Replace `YYYY-MM-DD` with today's date in ISO format.

- [ ] **Step 4: Verify**

Run:
```bash
wc -l .claude/skills/add-app/reference/freeshard-digest.md
jq . .claude/skills/add-app/reference/digest-meta.json
```
Expected: line count 100-400; jq prints valid JSON with `generated_at` and non-empty `source_urls`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/add-app/reference/freeshard-digest.md .claude/skills/add-app/reference/digest-meta.json
git commit -m "add-app: vendor freeshard docs digest"
```

---

## Task 5: Write phases/01-preflight.md

**Files:**
- Modify: `.claude/skills/add-app/phases/01-preflight.md`

- [ ] **Step 1: Write preflight.md**

```markdown
# Phase 1 — Preflight

Inputs: `$1` (app name argument).

Outputs (written to worktree scratch dir `./.add-app-scratch/`):
- `preflight.json` with `{name, mode}` where `mode ∈ {"new", "reeval"}`

## Steps

1. **Sanitize name.** Lowercase. Verify it matches `^[a-z0-9-]+$`. If not,
   print the invalid name and exit. The agent must not auto-correct.

2. **Check digest age.** Read `reference/digest-meta.json`. If
   `generated_at` is missing or more than 30 days before today, dispatch
   a `general-purpose` subagent with the same prompt used in
   `docs/superpowers/plans/2026-05-11-add-app-skill.md` Task 4 Step 1.
   Overwrite `reference/freeshard-digest.md` and
   `reference/digest-meta.json` with the new output. Commit the refresh
   as a separate commit before continuing: `chore: refresh freeshard
   docs digest`.

3. **Worktree setup.** Use the native `EnterWorktree` tool if available;
   otherwise `git worktree add .worktrees/add-<name> -b feat/add-<name>`.
   In reevaluation mode, branch is `feat/reeval-<name>`.

4. **Collision check.** Test for existence of `apps/<name>/` and
   `inactive_apps/<name>/`. If either exists, write
   `preflight.json` with `mode: "reeval"` and hand off to
   `phases/reeval.md`. Otherwise write `mode: "new"` and continue to
   `phases/02-research.md`.

5. **Scratch dir.** `mkdir -p .add-app-scratch/`. All inter-phase data
   lives here. The dir is gitignored automatically because the worktree
   is itself under `.claude/worktrees/`, which is ignored. The scratch
   dir lives at the worktree root, not in `.claude/`.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^## " .claude/skills/add-app/phases/01-preflight.md`
Expected: at least 1 (a top-level Steps section).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/01-preflight.md
git commit -m "add-app: write preflight phase"
```

---

## Task 6: Write phases/02-research.md

**Files:**
- Modify: `.claude/skills/add-app/phases/02-research.md`

- [ ] **Step 1: Write research.md**

```markdown
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

2. **Parse.** Extract the fenced JSON block to `research.json`. Extract
   the Notes section (everything after the JSON block) to
   `research_notes.md`.

3. **Validate required fields.** If any of `name`, `image`, `tag_latest`,
   `license_class`, `container_port`, `description_short` is missing or
   null in `research.json`, re-dispatch the subagent once with the
   missing fields named. If still missing, hard-exit with code a
   (treating image-related missing fields) or print findings and stop
   for others.

4. **Manifest inspect.** Run `docker manifest inspect <image>:<tag>`
   where `<tag>` is `tag_latest`. If exit code non-zero, hard-exit code
   a. Print the command output to the user.

5. **Apply hard exits.** Read `reference/exit-criteria.md`. Apply hard
   exits in order: a (already handled), b (`license_class != "foss"`),
   f (`paid == true` AND no free self-host tier per notes). On hard
   exit, print findings, do not commit anything, leave worktree for
   inspection, stop.

6. **Collect soft warnings.** Append to `research.json`'s `warnings[]`
   any of: c (privileged/gpu), d (multi-tenant), e (abandoned — compute
   from `last_release_date`), g (resource_class_estimate == "l").

7. **Hand off.** Continue to `phases/03-proposal.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^[0-9]\." .claude/skills/add-app/phases/02-research.md`
Expected: 7 (seven numbered steps).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/02-research.md
git commit -m "add-app: write research phase"
```

---

## Task 7: Write phases/03-proposal.md

**Files:**
- Modify: `.claude/skills/add-app/phases/03-proposal.md`

- [ ] **Step 1: Write proposal.md**

```markdown
# Phase 3 — Proposal

Inputs (in `./.add-app-scratch/`):
- `research.json`, `research_notes.md`

Outputs (in `./.add-app-scratch/`):
- `proposed_app_meta.json`
- `proposed_docker-compose.yml.template`
- `decisions.md` — rationale for access mode, volumes, lifecycle, telemetry

## Steps

1. **Read inputs.** Parse `research.json`. Read `research_notes.md` as
   plain text for nuanced decisions.

2. **Decide access mode.**
   - Default: `private` with the standard X-Ptl-Client-* headers from
     the template.
   - If `research_notes.md` documents auth-proxy support: use `private`
     with auth-proxy headers. Pick the username header env var from
     notes and add it to the compose template's environment block. Add
     `X-Ptl-User: admin` to the `paths[""].headers`.
   - If notes say the app handles its own auth and is intended for
     public sharing (e.g., ghost, immich): use `public`.

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

6. **Decide telemetry opt-out.** Read notes for env vars; include each
   in the compose template `environment:` block.

7. **Draft `proposed_app_meta.json`.** Use the schema in the digest.
   Required fields filled from `research.json`. `pretty_name` =
   titlecased name unless notes specify otherwise. `upstream_repo` set
   from research. `homepage` set if present.
   `store_info.description_short` from research; `description_long`
   from notes (parse paragraphs).

8. **Draft `proposed_docker-compose.yml.template`.** Use the patterns
   from the digest:
   - Single-container apps → minimal template
   - Multi-container apps (Postgres, Redis, etc.) → multi-network
     template with internal private network
   - Always include `BASE_URL=https://<name>.{{ portal.domain }}` if
     the app uses BASE_URL or similar
   - Pin image tag to `tag_latest`

9. **Write `decisions.md`.** Short rationale per decision (access mode,
   shared volume, lifecycle, telemetry, multi-container choice). Used
   later by PR body.

10. **Ambiguity gate.** If `research.json` has non-empty `ambiguity[]`,
    present a checkpoint to the user:
    - Show drafted files.
    - List each ambiguity topic with options and the subagent's
      recommendation.
    - User chooses per topic, edits drafts, or rejects.
    - Reject → hard exit, leave worktree in place.

11. **Hand off.** Continue to `phases/04-scaffold.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^[0-9]\+\." .claude/skills/add-app/phases/03-proposal.md`
Expected: 11.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/03-proposal.md
git commit -m "add-app: write proposal phase"
```

---

## Task 8: Write phases/04-scaffold.md

**Files:**
- Modify: `.claude/skills/add-app/phases/04-scaffold.md`

- [ ] **Step 1: Write scaffold.md**

```markdown
# Phase 4 — Scaffold

Inputs (in `./.add-app-scratch/`):
- `proposed_app_meta.json`, `proposed_docker-compose.yml.template`,
  `research.json`, `research_notes.md`

Outputs:
- `apps/<name>/app_meta.json`
- `apps/<name>/docker-compose.yml.template`
- `apps/<name>/icon.svg` or `icon.png` (or none)
- Modified `update.py` if tag-strip rule needed

## Steps

1. **Scaffold from template.** Run `just new-app <name>`. This copies
   `inactive_apps/template/` to `apps/<name>/` and substitutes
   `<<name>>`.

2. **Overwrite drafts.** Replace the scaffolded
   `apps/<name>/app_meta.json` with `proposed_app_meta.json`. Replace
   `apps/<name>/docker-compose.yml.template` with the proposed compose.

3. **Icon cascade.** Try in order; first success wins. Do not block on
   failure (proceed without icon).
   a. `curl -fsSL <upstream_repo>/raw/HEAD/logo.svg` (also try
      `icon.svg`, `assets/logo.svg`, `docs/logo.svg`)
   b. Fetch `<homepage>/favicon.ico` and inspect `<link rel="icon">` tags
      from `<homepage>/`. If the linked icon is SVG, download it. PNG
      is acceptable too.
   c. `<homepage>/apple-touch-icon.png`
   If something was fetched, save as `apps/<name>/icon.svg` (or
   `icon.png` if PNG), overwriting the scaffold's placeholder. Update
   `apps/<name>/app_meta.json`'s `icon` field accordingly. If nothing
   found, leave whatever the scaffold provided and add a note to
   `research_notes.md`: "Icon missing — please add manually."

4. **update.py entry.** If `research.json.tag_strip_v_needed == true`,
   open `update.py`, find the `adapt_version_string` function, and add
   `<name>` to the list of apps that strip the `v` prefix. Match
   surrounding style. If a different tag transformation is needed
   (suffix strip, prefix add), insert a custom branch and document the
   rule in `decisions.md`.

5. **Hand off.** Continue to `phases/05-pr.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^[0-9]\." .claude/skills/add-app/phases/04-scaffold.md`
Expected: 5.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/04-scaffold.md
git commit -m "add-app: write scaffold phase"
```

---

## Task 9: Write templates/pr-body.md

**Files:**
- Modify: `.claude/skills/add-app/templates/pr-body.md`

- [ ] **Step 1: Write pr-body.md**

```markdown
# {{ pretty_name }} — Add to Freeshard app store

**Upstream:** {{ upstream_repo }}
**Homepage:** {{ homepage }}
**License:** {{ license }} ({{ license_class }})
**Image:** `{{ image }}:{{ tag_latest }}`
**Last release:** {{ last_release_date }}

## What is it

{{ description_short }}

{{ description_long }}

## Integration decisions

{{ decisions }}

## Soft warnings

{{ warnings_bulleted_or_none }}

## Rejected image candidates

{{ rejected_images_bulleted_or_none }}

## Notes from research

{{ research_notes }}

## Checklist (from agents.md)

- [x] `just new-app <name>`
- [x] Docker image identified ({{ image }}, tag {{ tag_latest }})
- [x] `docker-compose.yml.template` set
- [x] `app_meta.json` set (`app_version`, `name`, `pretty_name`, `icon`, `entrypoints`, `paths`, `lifecycle`, `store_info`)
- [x] `upstream_repo` set
- [{{ icon_done }}] Icon present
- [{{ auth_proxy_done }}] Auth-proxy configured (if applicable)
- [{{ shared_data_done }}] Shared data path mounted (if applicable)
- [{{ portal_size_done }}] `minimum_portal_size` set (if applicable)
- [{{ always_on_done }}] `always_on` set (if applicable)
- [{{ telemetry_done }}] Telemetry/analytics disabled (if applicable)
- [x] `docker manifest inspect` passed

## Follow-ups

{{ follow_ups_bulleted_or_none }}
```

A second template, for reevaluation, follows the same shape but adds a
`## Diff summary` section at the top showing what changed and a
`## Removal recommendation` section if license flipped non-FOSS.
Include that variant inline below the first template, separated by
`---` and prefixed with a `# Reevaluation PR body` heading.

- [ ] **Step 2: Add the reevaluation variant**

Append to the same file:

```markdown
---

# Reevaluation PR body

# Reevaluate {{ pretty_name }}

## Diff summary

{{ diff_summary }}

## Why now

{{ reevaluation_reasons }}

## Changes made

{{ changes_bulleted }}

## Removal recommendation

{{ removal_recommendation_or_none }}

## Notes from research

{{ research_notes }}
```

- [ ] **Step 3: Verify**

Run: `grep -c "{{" .claude/skills/add-app/templates/pr-body.md`
Expected: at least 15 placeholder substitutions.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/add-app/templates/pr-body.md
git commit -m "add-app: write PR body template"
```

---

## Task 10: Write phases/05-pr.md

**Files:**
- Modify: `.claude/skills/add-app/phases/05-pr.md`

- [ ] **Step 1: Write 05-pr.md**

```markdown
# Phase 5 — PR

Inputs:
- All files in `apps/<name>/`
- `./.add-app-scratch/research.json`, `research_notes.md`, `decisions.md`
- `templates/pr-body.md`

Outputs:
- A GitHub PR (never draft)
- The PR URL printed to the user

## Steps

1. **Verify worktree is the expected branch.** `git branch --show-current`
   must equal `feat/add-<name>`.

2. **Stage and commit.**
   ```bash
   git add apps/<name>/ update.py
   git commit -m "feat: add <name>"
   ```
   If `update.py` was not modified, drop it from the `git add`.

3. **Push.**
   ```bash
   git push -u origin feat/add-<name>
   ```

4. **Render PR body.** Read `templates/pr-body.md` (the first variant,
   above the `---`). Substitute placeholders from `research.json`,
   `decisions.md`, `research_notes.md`. For checklist items, set
   `[x]` if applicable and present, `[ ]` if the feature does not apply
   to this app (leave unchecked; do not include a "not applicable"
   note).

5. **Create PR.**
   ```bash
   gh pr create \
     --title "Add <pretty_name>" \
     --body "$(cat /tmp/pr-body-rendered.md)"
   ```
   Never use `--draft`.

6. **Print URL.** Print the PR URL from `gh pr create`'s output.

7. **Done.** Worktree remains in place. The user reviews on GitHub.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^[0-9]\." .claude/skills/add-app/phases/05-pr.md`
Expected: 7.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/05-pr.md
git commit -m "add-app: write PR phase"
```

---

## Task 11: Write phases/reeval.md

**Files:**
- Modify: `.claude/skills/add-app/phases/reeval.md`

- [ ] **Step 1: Write reeval.md**

```markdown
# Reevaluation mode

Triggered by preflight when `apps/<name>/` or `inactive_apps/<name>/`
exists.

Inputs: `name` from preflight scratch.

## Steps

1. **Worktree.** Branch is `feat/reeval-<name>`.

2. **Load current.** Read `apps/<name>/app_meta.json` and
   `apps/<name>/docker-compose.yml.template`. Save to scratch as
   `current_app_meta.json`, `current_compose.yml`.

3. **Research.** Dispatch the same research subagent prompt as
   `phases/02-research.md` Step 1. Save outputs to
   `./.add-app-scratch/research.json` and `research_notes.md`.

4. **Manifest inspect** on the latest tag. If image moved (image org/name
   changed), inspect the new image. Hard exit a on failure.

5. **Hard exits.** Same as new-app mode: b (license flipped non-FOSS),
   f (became paid). On hard exit b, write a removal-recommendation PR
   instead of stopping: title "Reevaluate <name> — consider removal",
   body explains why, no scaffold changes. Continue to commit/PR steps
   with no `apps/<name>/` modifications other than this PR description.

6. **Diff.** Compute differences between current and latest:
   - `current.app_version` vs `research.tag_latest`
   - image name/tag string vs `research.image:tag_latest`
   - env vars present in current vs documented in
     `research_notes.md` (new required, deprecated)
   - `auth_proxy_support` change (gained / lost)
   - container port change
   - agents.md best-practice drift (compare current
     `app_meta.json` shape against the schema in the digest:
     missing `upstream_repo`, missing `v: "1.2"` upgrade
     opportunity, missing telemetry opt-outs documented in notes,
     etc.)

7. **Classify diff.** Significant changes = anything in step 6 except
   pure version bump. If only `app_version` and image tag changed:
   print:
   ```
   Only version change detected: <current> → <new>
   Run `python update.py update --only <name>` instead.
   ```
   Exit (no PR).

8. **Propose.** For each significant change, draft the update. Same
   patterns as `phases/03-proposal.md`. Ambiguity gate same as new-app
   mode.

9. **Write changes** to `apps/<name>/`.

10. **PR.** Use the reevaluation variant of `templates/pr-body.md`.
    Title: `Reevaluate <pretty_name>` (or `... — consider removal`).
    Same `gh pr create` flow as `phases/05-pr.md`. Never draft.
```

- [ ] **Step 2: Verify**

Run: `grep -c "^[0-9]\+\." .claude/skills/add-app/phases/reeval.md`
Expected: 10.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/phases/reeval.md
git commit -m "add-app: write reevaluation phase"
```

---

## Task 12: Write SKILL.md (orchestration)

**Files:**
- Modify: `.claude/skills/add-app/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: add-app
description: Use when adding a new app to the Freeshard app repository. Researches the app, decides Freeshard fit, drafts integration files, and opens a PR. Detects existing apps and switches to reevaluation mode automatically. Triggered by /add-app <name>.
---

# add-app

Add or reevaluate a Freeshard app in this repository. Argument: the
app name (lowercase, dashes only).

## When to use

- `/add-app <name>` — add a new app, or reevaluate an existing one.
- User says "add app X to the store", "integrate X", "reevaluate X".

## Flow

The skill runs as five phases in sequence. Each phase has its own file
under `phases/`. Each phase reads from and writes to the worktree
scratch dir `./.add-app-scratch/`. Each phase file describes its own
inputs, outputs, and steps; follow them in order.

1. Preflight — `phases/01-preflight.md`
2. Research — `phases/02-research.md`
3. Proposal — `phases/03-proposal.md`
4. Scaffold — `phases/04-scaffold.md`
5. PR — `phases/05-pr.md`

If preflight detects the app already exists, jump from phase 1
directly to `phases/reeval.md` (reevaluation mode), skipping phases
2-5.

## References

- `reference/freeshard-digest.md` — compact summary of
  `docs.freeshard.net`. Read by the research subagent and the proposal
  phase. Auto-refreshed in preflight if older than 30 days.
- `reference/exit-criteria.md` — hard/soft exit rules and license
  classification.
- `templates/pr-body.md` — PR body templates (new-app and
  reevaluation variants).

## Principles

- Do not interact with the user unless the research subagent reported
  ambiguity. The PR is the gate.
- Hard exits (a/b/f) stop the run with findings printed; no PR.
- Soft warnings (c/d/e/g) render in the PR body; never stop the run.
- Never open a PR as draft.
- Leave the worktree in place after exit (success or hard exit) so the
  user can inspect.
```

- [ ] **Step 2: Verify**

Run: `head -3 .claude/skills/add-app/SKILL.md`
Expected: starts with `---` frontmatter line.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/add-app/SKILL.md
git commit -m "add-app: write SKILL.md orchestration"
```

---

## Task 13: Write the slash command

**Files:**
- Modify: `.claude/commands/add-app.md`

- [ ] **Step 1: Write add-app.md**

```markdown
---
description: Add a new app to the Freeshard app repository (or reevaluate an existing one)
argument-hint: <app-name>
---

Invoke the `add-app` skill with the argument `$1` (the app name).

The skill handles everything: research, suitability check, file
drafting, worktree, and PR. It will only stop and ask if the research
subagent reported ambiguity. Otherwise it runs end-to-end and prints
the PR URL.
```

- [ ] **Step 2: Verify**

Run: `cat .claude/commands/add-app.md`
Expected: shows frontmatter with `argument-hint: <app-name>`.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/add-app.md
git commit -m "add-app: register slash command"
```

---

## Task 14: Smoke test (manual, end-to-end)

**Files:** None modified.

This task verifies the skill works against a real, well-understood app
that is **not yet** in the repository, plus one that **is**, to
exercise both modes.

- [ ] **Step 1: Pick test candidates**

- New-app candidate: a small, known-FOSS, single-container app not yet
  in `apps/`. Check `ls apps/` for what's already there, then pick
  something like `homepage`, `vaultwarden`, `gotify`, or similar.
- Reevaluation candidate: any existing app, e.g. `linkding`.

- [ ] **Step 2: Run /add-app on the new-app candidate**

From the worktree (or main, since the skill creates its own worktree):

```
/add-app <candidate>
```

Expected behavior:
- New worktree at `.claude/worktrees/add-<candidate>` or
  `.worktrees/add-<candidate>` on `feat/add-<candidate>`.
- Subagent runs research, returns JSON + notes.
- `docker manifest inspect` runs and succeeds.
- `apps/<candidate>/` populated with `app_meta.json`, compose
  template, and (ideally) an icon.
- PR opened on GitHub, ready-for-review (not draft).

Verify by reading the generated files. Do **not** merge the PR — close
it after inspection.

- [ ] **Step 3: Run /add-app on the reevaluation candidate**

```
/add-app linkding
```

Expected:
- Skill detects collision in preflight.
- Switches to reevaluation mode.
- Either exits with "only version drift, run update.py" (most likely
  for a well-maintained app), or opens a "Reevaluate linkding" PR.

- [ ] **Step 4: Run /add-app on a known non-FOSS app to test hard exit**

Pick an app with a source-available license, e.g. `redis` (image
exists, license is RSAL/SSPL since 7.4). Expected: hard exit b, no
PR, findings printed.

- [ ] **Step 5: Document any deviations**

If the skill misbehaved in any of the three runs, capture the
deviation in a follow-up note (file a GitHub issue or amend
`agents.md`). Common things to watch for:
- Research subagent invented data
- License classifier mismapped
- Icon cascade picked something ugly (acceptable per design, but
  worth recording for tuning)
- Ambiguity gate fired unexpectedly
- PR body placeholder substitution missed

- [ ] **Step 6: Commit any fixes**

If fixes are needed, commit them per the patterns in earlier tasks.

---

## Task 15: File follow-up issue for CI-driven digest regeneration

**Files:** None modified (issue created in the docs repository, not in
this repo).

- [ ] **Step 1: Locate the docs repository**

Probably at `/home/ubuntu/projects/freeshard/documentation/`. Check
`git remote -v` from inside it to confirm.

- [ ] **Step 2: Open the issue**

From the docs repo:

```bash
gh issue create \
  --title "Add CI-driven AI-optimized docs digest" \
  --body "$(cat <<'EOF'
The app-repository's `add-app` skill vendors a compact AI-optimized
digest of these docs at `.claude/skills/add-app/reference/freeshard-digest.md`.
It self-refreshes when older than 30 days, but this is a fallback. The
better long-term solution is for the docs site to publish an
authoritative digest as part of CI.

Proposed:
- A `digest.md` artifact generated by docs CI on every release (or
  weekly), checked into the docs repo or published alongside the docs
  site.
- The add-app skill (and any future skills) fetches it instead of
  crawling the docs site.

Once available, the 30-day local refresh becomes a no-op safety net.
EOF
)"
```

- [ ] **Step 3: Note the issue URL in the design doc**

Edit `docs/superpowers/specs/2026-05-10-add-app-skill-design.md`, find
the "Freeshard docs digest" section, and append the issue URL.

Commit:

```bash
git add docs/superpowers/specs/2026-05-10-add-app-skill-design.md
git commit -m "spec: link CI digest follow-up issue"
```

---

## Self-review checklist (for the executing agent)

After completing all tasks:

- [ ] All 11 skill files exist and are non-stub
- [ ] `/add-app linkding` invokes the skill (test via Claude Code)
- [ ] `git status` is clean in the worktree
- [ ] All commits follow the format `add-app: ...` or `chore: ...` or `feat: ...`
- [ ] The spec at `docs/superpowers/specs/2026-05-10-add-app-skill-design.md` is unchanged structurally (only the follow-up issue link added in Task 15)
- [ ] No accidental edits to `apps/` or `inactive_apps/` (those are touched only when the skill is actually run, not during plan implementation)
