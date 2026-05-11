# add-app skill — design

Date: 2026-05-10
Status: design approved, pending implementation

## Goal

A skill living in `app-repository/.claude/skills/add-app/`, invokable via `/add-app <name>`, that researches an app, decides whether it fits Freeshard, drafts the integration files, and opens a PR. The skill must end at a PR (rich body, never draft) without requiring user interaction when the integration is unambiguous.

If the app already exists, the skill switches into reevaluation mode: it diffs the current integration against latest upstream and current best-practice, and either exits with a hint to use `update.py` (version-only drift) or opens a "Reevaluate <name>" PR.

## Layout

```
app-repository/
├── .claude/
│   ├── skills/
│   │   └── add-app/
│   │       ├── SKILL.md                    # main skill, invokes phases
│   │       ├── phases/
│   │       │   ├── 01-preflight.md
│   │       │   ├── 02-research.md
│   │       │   ├── 03-proposal.md
│   │       │   ├── 04-scaffold.md
│   │       │   ├── 05-pr.md
│   │       │   └── reeval.md               # alternate flow when app exists
│   │       ├── reference/
│   │       │   ├── freeshard-digest.md     # compact, AI-optimized doc summary (vendored)
│   │       │   ├── digest-meta.json        # {generated_at, source_urls[]}
│   │       │   └── exit-criteria.md        # hard/soft rules table, license classes
│   │       └── templates/
│   │           └── pr-body.md
│   └── commands/
│       └── add-app.md                      # slash command → invokes skill
```

The skill is named `add-app`. Reevaluation is the same skill switched into a different phase set when preflight detects a collision; no separate command.

## Exit criteria

| Code | Condition | Type | Action |
|------|-----------|------|--------|
| a | No official Docker image | hard | exit, print findings, no PR |
| b | Non-FOSS license (`source-available` or `proprietary`) | hard | exit, print findings, no PR |
| c | Requires GPU / kernel modules / privileged | soft | render warning in PR body |
| d | Multi-tenant SaaS architecture | soft | render warning in PR body |
| e | Abandoned (no release in 12+ months) | soft | render warning in PR body |
| f | Paid / license-key required (no free self-host tier) | hard | exit, print findings, no PR |
| g | Heavy idle RAM (>2 GB) | soft | render warning in PR body, set `minimum_portal_size` |
| h | Already in `apps/` or `inactive_apps/` | route | switch to reevaluation mode |

`license_class` mapping is documented in `reference/exit-criteria.md`. MIT, Apache-2.0, BSD-*, GPL-*, AGPL, MPL → `foss`. BSL, SSPL, Elastic, "source-available" → `source-available`. Anything else → `proprietary`. Both non-FOSS classes trigger hard exit b.

## Phase flow (new app)

```
/add-app <name>
  ↓
1. Preflight
   - sanitize name (regex ^[a-z0-9-]+$, lowercase)
   - check digest age (refresh if >30d via subagent)
   - check apps/<name> and inactive_apps/<name> → if exists, route to reevaluation
  ↓
2. Research
   - dispatch general-purpose subagent with prompt anchored on freeshard-digest.md
   - subagent returns single JSON block (schema below)
   - main thread parses; missing required fields → re-ask once, else hard exit
   - immediately run `docker manifest inspect <image>:<tag>` (fail-fast → hard exit a)
   - apply hard-exit checks (b, f) → hard exit if triggered
   - collect soft warnings (c, d, e, g) into a list
  ↓
3. Proposal
   - draft app_meta.json + docker-compose.yml.template in memory
   - decide access model (private / public / auth-proxy) — reads notes for auth-proxy env vars and quirks
   - decide shared volumes (fs.shared/...) — reads notes for data-category hints
   - decide minimum_portal_size from resource_class_estimate
   - decide always_on / idle_time_for_shutdown
   - decide telemetry opt-out env vars — reads notes
   - if subagent reported any ambiguity[] entries → checkpoint with user
   - else continue silently
  ↓
4. Scaffold
   - run `just new-app <name>` (in worktree)
   - overwrite generated files with drafts
   - icon: cascade GitHub repo logo → homepage favicon (SVG only) → apple-touch-icon.png; accept whatever found, no placeholder, do not block
   - if image tag != GitHub release tag, add entry to update.py:adapt_version_string
  ↓
5. PR
   - commit
   - `gh pr create` with rich body, never draft
```

The terminal state is a PR URL printed to the user. PR is the gate — user reviews there.

### Worktree

Each run uses an isolated worktree at `.worktrees/add-<name>` on branch `feat/add-<name>` (or `feat/reeval-<name>` for reevaluation). Created via the `EnterWorktree` native tool when available, falling back to `git worktree add`.

## Research subagent contract

Subagent type: `general-purpose`. Prompt (in `phases/02-research.md`) instructs it to investigate the app via Docker Hub, GitHub, and the upstream homepage, anchored on the contract below.

The contract is **hybrid**: a structured JSON block carries fields the main thread needs for programmatic gating, followed by a free-form markdown `notes` section for everything else. The main thread parses the JSON for hard-exit checks, version comparison, and file drafting. The `notes` section is never parsed for gating — it is rendered verbatim into the PR body so reviewers see the subagent's nuanced findings.

Return format:

````
```json
{
  "name": "linkding",
  "homepage": "https://linkding.link",
  "upstream_repo": "https://github.com/sissbruecker/linkding",
  "license": "MIT",
  "license_class": "foss",
  "paid": false,
  "image": "sissbruecker/linkding",
  "tag_latest": "1.36.0",
  "github_release_tag_example": "v1.36.0",
  "tag_strip_v_needed": true,
  "last_release_date": "2025-09-12",
  "abandoned": false,
  "container_port": 9090,
  "needs_database": false,
  "supporting_services": [],
  "resource_class_estimate": "xs",
  "multi_tenant": false,
  "needs_privileged": false,
  "needs_gpu": false,
  "icon_candidates": ["..."],
  "description_short": "Self-hosted bookmark manager.",
  "ambiguity": [],
  "warnings": []
}
```

## Notes

<free-form markdown — subagent dumps anything important that doesn't fit the schema: auth-proxy details, deployment quirks, security caveats, federation requirements, registry caveats, screenshots, long description, env vars to disable telemetry, alternative image candidates considered and rejected, etc.>
````

Rationale for hybrid:
- **Structured fields** = deterministic gating. Hard exits (a/b/f), version-only-drift check, and file drafting need parsed values, not LLM re-extraction.
- **Free-form `notes`** = room for surprise findings the schema can't anticipate.

Structured field rules:
- Enums kept minimal: `license_class ∈ {foss, source-available, proprietary}`, `resource_class_estimate ∈ {xs, s, l}`. Anything weirder lives in `notes`.
- No `tag_format` enum — the main thread decides `tag_strip_v_needed` from `tag_latest` vs `github_release_tag_example` directly; unusual schemes (date stamps, monotonic build numbers) get described in `notes`.
- No structured `auth_proxy_support`, `shared_volume_hint`, `telemetry_optout_env` — these live in `notes` because they're nuanced (often partial support, plugin-only, multiple alternative envs). Proposal phase reads `notes` to decide.
- `ambiguity[]` and `warnings[]` stay structured because they drive checkpoint logic and PR-body sections.

Required JSON fields (main thread validates): `name`, `image`, `tag_latest`, `license_class`, `container_port`, `description_short`. Missing → re-ask once, else hard exit.

`ambiguity[]` entries: `{topic, options[], recommendation}`. Non-empty triggers checkpoint.
`warnings[]` entries: plain strings; rendered in PR body.

## Multiple-image disambiguation

When more than one Docker image plausibly matches the app, the subagent picks the most-official by this priority and lists rejects in `warnings[]` for the PR body:

1. Image org matches GitHub org of `upstream_repo`
2. Image is linked from upstream README/docs
3. Docker Hub "official" / "verified publisher" badge
4. Highest pull count

Multiple images on their own do not trigger a checkpoint.

## Adaptive interaction — when to checkpoint

The skill runs end-to-end with no user interaction unless ambiguity is detected. Checkpoint fires only when the subagent's `ambiguity[]` is non-empty, or the main thread cannot make a decision, e.g.:

- Container port unambiguous: yes if no
- Multi-container setup clearly documented: yes if no
- Auth-proxy clearly supported or clearly absent: yes if partial/conflicting
- Conflicting facts across sources

Things that do NOT trigger a checkpoint:
- Multiple plausible images (heuristic picks)
- Soft warnings (c/d/e/g)
- Missing icon
- Unusual tag format (handled by `update.py` entry)
- Large resource class (set `minimum_portal_size`)

When checkpoint fires, the skill shows the drafted files plus a list of `ambiguity[]` topics with options and recommendations. User picks per topic, or rejects (hard exit, worktree left in place for inspection).

## Reevaluation mode

Triggered when preflight finds `apps/<name>/` or `inactive_apps/<name>/` exists (criterion h).

```
preflight → existing app
  ↓
load current app_meta.json + compose template
  ↓
research subagent (same contract as new-app flow)
  ↓
diff: current vs latest upstream + current vs digest best-practice
  ↓
classify diff
  ↓
significant non-version changes?
  no  → EXIT: "only version drift, run python update.py update --only <name>"
  yes → reevaluation proposal (version bump + compose changes + app_meta changes + agents.md drift fixes)
        ↓
        ambiguity? → checkpoint, else proceed silently
        ↓
        write changes (in worktree)
        ↓
        PR: "Reevaluate <name>" with rich body diff summary
```

Significant non-version changes (any of):
- Image org/name changed (upstream renamed)
- New required env var (e.g., new auth, telemetry)
- Deprecated env var still in template
- New auth-proxy support upstream gained
- License class changed
- Container port changed
- agents.md best-practice drift (e.g., template uses old `v` field, missing `upstream_repo`, missing telemetry opt-out)
- Hard-exit criteria now triggered (license flipped to non-FOSS) → propose removal in PR body

Version-only drift:
```
Only version change detected: 1.36.0 → 1.37.0
Run `python update.py update --only <name>` instead.
```

Branch: `feat/reeval-<name>`. PR title: `Reevaluate <name>`.

## Pre-PR verification

`docker manifest inspect <image>:<tag>` runs at end of phase 2 (research), as soon as image+tag are known. Failure = hard exit a (no Docker image). No further checks (no compose render, no `build_store_data` — CI handles the build artifact).

## PR body

Rendered from `templates/pr-body.md`. Always opens ready-for-review (never draft). Includes:

- App summary, license, upstream repo, homepage
- Selected Docker image with rationale (especially when multiple were considered)
- Access model decision and rationale (private / public / auth-proxy + relevant env vars)
- Soft warnings (if any)
- Ticked checklist mirroring agents.md "Checklist for Adding a New App"
- Follow-up notes (e.g., "icon missing, please add", "abandoned upstream — monitor")

Reevaluation PRs additionally include a diff summary section.

## Freeshard docs digest

Vendored at `reference/freeshard-digest.md` with companion `digest-meta.json` (`generated_at`, `source_urls`). Compact AI-optimized summary of `docs.freeshard.net` — covers app model, access modes, template variables, lifecycle, networking, common patterns. Used to anchor the research subagent's prompt and the proposal phase's decisions.

Drift handling: preflight checks `generated_at`. If older than 30 days, dispatch a subagent to crawl `docs.freeshard.net`, regenerate the digest, and overwrite both files before continuing.

Follow-up: file an issue in the docs repo to add CI-driven digest regeneration so the vendored copy is always fresh and the 30-day refresh becomes a fallback.

## Slash command

`app-repository/.claude/commands/add-app.md` — thin wrapper that invokes the skill with `$1` as the app name. Routes to reevaluation automatically based on collision detection inside the skill (no separate command).

## Out of scope

- Building zip artifacts (CI handles `python -m build_store_data`)
- Running the app for runtime verification
- Updating already-present apps for version bumps only (use `update.py`)
- Deleting apps when they fail reevaluation (PR body just proposes removal)
