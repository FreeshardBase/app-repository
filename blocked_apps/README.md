# Blocked apps

Apps that were researched for inclusion in the Freeshard app store but did
not pass the inclusion criteria. Kept here so future agents and humans do
not waste time re-analysing the same app, and so that a record exists of
why each candidate was turned down.

Each file is named `<app-name>.md` (lowercase, dashes only — same
convention as `apps/` and `inactive_apps/`).

## File schema

```markdown
# <Pretty Name>

**Blocked:** YYYY-MM-DD
**Exit code:** <a | b | f | j | reject>
**Reason:** one-line summary

| Field | Value |
|---|---|
| Homepage | ... |
| Upstream repo | ... |
| License | <name> (<class>) |
| Image | <image>:<tag> |
| Description | ... |
| Paid | true / false |
| Auth-proxy | supported / not supported |

## Reason for block

Multi-sentence explanation of which exit criterion fired and the specific
evidence (license text, missing image, paid tier requirement, etc.).

## Research notes

Verbatim or trimmed copy of `.add-app-scratch/research_notes.md` from the
add-app run — auth-proxy support, telemetry, deployment quirks, etc.
Useful if the app is reconsidered later under different criteria.
```

Exit codes match `.claude/skills/add-app/reference/exit-criteria.md`:

| Code | Meaning |
|---|---|
| a | No official Docker image |
| b | Non-FOSS license |
| f | Paid / license-key required |
| j | First-run bootstrap requires shell access |
| reject | User rejected during ambiguity gate in phase 3 |

## Reconsidering a blocked app

If upstream changes (license relicensed to FOSS, image published, free
tier added), delete the file and re-run `/add-app <name>`.
