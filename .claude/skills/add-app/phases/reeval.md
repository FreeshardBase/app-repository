# Reevaluation mode

Triggered by preflight when `apps/<name>/` or `inactive_apps/<name>/` exists.

Inputs: `name` from preflight scratch.

## Steps

1. **Worktree.** Branch is `feat/reeval-<name>`.

2. **Load current.** Read `apps/<name>/app_meta.json` and `apps/<name>/docker-compose.yml.template`. Save to scratch as `current_app_meta.json`, `current_compose.yml`.

3. **Research.** Dispatch the same research subagent prompt as `phases/02-research.md` Step 1. Save outputs to `./.add-app-scratch/research.json` and `research_notes.md`.

4. **Manifest inspect** on the latest tag. If image moved (image org/name changed), inspect the new image. Hard exit a on failure.

5. **Hard exits.** Same as new-app mode: b (license flipped non-FOSS), f (became paid). On hard exit b, write a removal-recommendation PR instead of stopping: title "Reevaluate <name> — consider removal", body explains why, no scaffold changes. Continue to commit/PR steps with no `apps/<name>/` modifications other than this PR description.

6. **Diff.** Compute differences between current and latest:
   - `current.app_version` vs `research.tag_latest`
   - image name/tag string vs `research.image:tag_latest`
   - env vars present in current vs documented in `research_notes.md` (new required, deprecated)
   - `auth_proxy_support` change (gained / lost)
   - container port change
   - agents.md best-practice drift (compare current `app_meta.json` shape against the schema in the digest: missing `upstream_repo`, missing `v: "1.2"` upgrade opportunity, missing telemetry opt-outs documented in notes, etc.)

7. **Classify diff.** Significant changes = anything in step 6 except pure version bump. If only `app_version` and image tag changed: print:
   ```
   Only version change detected: <current> → <new>
   Run `python update.py update --only <name>` instead.
   ```
   Exit (no PR).

8. **Propose.** For each significant change, draft the update. Same patterns as `phases/03-proposal.md`. Ambiguity gate same as new-app mode.

9. **Write changes** to `apps/<name>/`.

10. **PR.** Use the reevaluation variant of `templates/pr-body.md`. Title: `Reevaluate <pretty_name>` (or `... — consider removal`). Same `gh pr create` flow as `phases/05-pr.md`. Never draft.
