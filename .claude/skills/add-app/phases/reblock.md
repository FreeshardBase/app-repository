# Reblock check

Triggered by preflight when `blocked_apps/<name>.md` exists.

Inputs:
- `name` from preflight scratch
- `blocked_apps/<name>.md` — the prior block record

Purpose: confirm the original exit criterion still holds. If it does,
abort with no changes. If it no longer holds, remove the block record
and re-enter the full add-app flow from phase 2.

## Steps

1. **Read the block record.** Parse `blocked_apps/<name>.md` and
   extract the `Exit code`, `Reason`, `License`, `Image`, `Paid`, and
   `Blocked:` date fields. Save to `./.add-app-scratch/prior_block.json`
   for downstream phases.

2. **Announce to the user.** Print a short summary before doing any
   network calls:

   ```
   Found prior block: blocked_apps/<name>.md
     Exit code: <code>
     Blocked:   <date>
     Reason:    <one-line reason>
   Re-checking whether the criterion still holds...
   ```

3. **Targeted recheck.** Dispatch the narrowest check that proves or
   disproves the prior exit. Do NOT run the full research subagent at
   this stage — it is wasted work if the block still holds.

   | Exit code | Recheck |
   |---|---|
   | `a` | `docker manifest inspect <image>:<tag>` from the record. If the image was never identified, dispatch a narrow research subagent: "locate any official Docker image for <name>; return image:tag or null". |
   | `b` | Fetch the upstream LICENSE file (`gh api repos/<org>/<repo>/contents/LICENSE` or WebFetch). Classify per `reference/exit-criteria.md`. |
   | `f` | WebFetch the upstream pricing/self-host docs page. Confirm whether a free self-host tier exists. |
   | `j` | WebFetch the upstream first-run / installation docs. Confirm whether shell access is still required for initial admin creation. |
   | `reject` | Print the prior ambiguity that led to rejection (from the file) and ask the user whether the rejection still stands. This is the only recheck that requires user input. |

4. **Decide.**

   - **Block still holds.** Stop. Do not modify any files. Print:

     ```
     Block still applies (<code>). Evidence: <what the recheck showed>.
     No changes made. Worktree left for inspection.
     ```

     If the recheck confirmed the same reason but on a newer date,
     optionally update only the `Blocked:` date line in
     `blocked_apps/<name>.md` and commit
     `docs(blocked_apps): refresh <name> recheck date` — but do not
     open a PR for a date-only bump.

   - **Block no longer holds.** Remove `blocked_apps/<name>.md`, then
     commit:

     ```
     docs(blocked_apps): remove <name> — <code> no longer applies (<short reason>)
     ```

     Then re-enter the full new-app flow at `phases/02-research.md`.
     The branch stays `feat/add-<name>`; subsequent phases append
     commits to it. The eventual PR body (templated by
     `phases/05-pr.md`) MUST mention the prior block and what changed
     upstream.

5. **Scratch.** Keep `prior_block.json` in `./.add-app-scratch/` so
   `phases/05-pr.md` can reference it when drafting the PR body.
