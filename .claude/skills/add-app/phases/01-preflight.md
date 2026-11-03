# Phase 1 — Preflight

Inputs: `$1` (app name argument).

Outputs (written to worktree scratch dir `./.add-app-scratch/`):
- `preflight.json` with `{name, mode}` where `mode ∈ {"new", "reeval", "reblock"}`

## Steps

1. **Sanitize name.** Lowercase. Verify it matches `^[a-z0-9-]+$`. If not, print the invalid name and exit. Do not auto-correct.

2. **Worktree setup.** Use the native `EnterWorktree` tool if available; otherwise `git worktree add .worktrees/add-<name> -b feat/add-<name>`. In reevaluation mode, branch is `feat/reeval-<name>`.

3. **Fetch the docs digest.** `mkdir -p .add-app-scratch && curl -fsSL https://raw.githubusercontent.com/FreeshardBase/documentation/main/digest.md -o .add-app-scratch/freeshard-digest.md`. This is the AI-optimized digest of `docs.freeshard.net`, maintained in the documentation repo alongside the docs it summarizes; every later phase reads it from the scratch dir. If the download fails, stop and report it. Do not crawl `docs.freeshard.net` or write a digest yourself instead.

4. **Collision check.** Test for existence of `apps/<name>/`, `inactive_apps/<name>/`, and `blocked_apps/<name>.md`. First match wins, in this order:
   - `apps/<name>/` or `inactive_apps/<name>/` → write `preflight.json` with `mode: "reeval"` and hand off to `phases/reeval.md`.
   - `blocked_apps/<name>.md` → write `preflight.json` with `mode: "reblock"` and hand off to `phases/reblock.md`. **Always announce to the user**: print the existing block reason and exit code from the file before the recheck begins, so the user understands why the flow is diverging.
   - Otherwise → write `mode: "new"` and continue to `phases/02-research.md`.

5. **Scratch dir.** `.add-app-scratch/` exists from step 3. All inter-phase data lives here. The dir is gitignored automatically because the worktree is itself under `.claude/worktrees/`, which is ignored. The scratch dir lives at the worktree root, not in `.claude/`.
