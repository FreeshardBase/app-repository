---
name: add-app
description: Use when adding a new app to the Freeshard app repository. Researches the app, decides Freeshard fit, drafts integration files, and opens a PR. Detects existing apps and switches to reevaluation mode automatically. Triggered by /add-app <name>.
---

# add-app

Add or reevaluate a Freeshard app in this repository. Argument: the app name (lowercase, dashes only).

## When to use

- `/add-app <name>` — add a new app, or reevaluate an existing one.
- User says "add app X to the store", "integrate X", "reevaluate X".

## Flow

The skill runs as five phases in sequence. Each phase has its own file under `phases/`. Each phase reads from and writes to the worktree scratch dir `./.add-app-scratch/`. Each phase file describes its own inputs, outputs, and steps; follow them in order.

1. Preflight — `phases/01-preflight.md`
2. Research — `phases/02-research.md`
3. Proposal — `phases/03-proposal.md`
4. Scaffold — `phases/04-scaffold.md`
5. PR — `phases/05-pr.md`

If preflight detects the app already exists, jump from phase 1 directly to `phases/reeval.md` (reevaluation mode), skipping phases 2-5.

## References

- `reference/freeshard-digest.md` — compact summary of `docs.freeshard.net`. Read by the research subagent and the proposal phase. Auto-refreshed in preflight if older than 30 days.
- `reference/exit-criteria.md` — hard/soft exit rules and license classification.
- `reference/deployment-gotchas.md` — recurring integration failure modes (non-root image bind-mount EACCES, all-prerelease repos). Consult in phases 3–4.
- `templates/pr-body.md` — PR body templates (new-app and reevaluation variants).

## Principles

- Do not interact with the user unless the research subagent reported ambiguity. The PR is the gate.
- Hard exits (a/b/f) stop the run with findings printed; no PR.
- Soft warnings (c/d/e/g) render in the PR body; never stop the run.
- Never open a PR as draft.
- Leave the worktree in place after exit (success or hard exit) so the user can inspect.
