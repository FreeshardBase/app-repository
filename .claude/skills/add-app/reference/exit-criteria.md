# Exit Criteria

## Hard exits (skill stops scaffolding, opens documentation-only PR)

| Code | Trigger | Detection |
|---|---|---|
| a | No official Docker image | `docker manifest inspect <image>:<tag>` returns non-zero, or research subagent could not locate any image |
| b | Non-FOSS license | `license_class ∈ {source-available, proprietary}` |
| f | Paid / license-key required | `paid == true` AND no documented free self-host tier |
| j | First-run bootstrap requires shell access | App has built-in auth, admin user cannot self-register, and creation requires `docker exec` / SSH. Freeshard shard owners have no shell access to app containers. See `phases/03-proposal.md` step 2a for workaround priority before applying this exit. |
| reject | User rejected proposal at ambiguity gate | Phase 3 step 10 — user does not approve drafted files |

On any hard exit, the skill MUST still document the analysis by writing
`blocked_apps/<name>.md` and opening a small documentation-only PR. See
"Blocked-app documentation" below for the schema and procedure.

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

## Blocked-app documentation

Every hard exit results in a file at `blocked_apps/<name>.md` so the next
agent does not waste time re-researching the same app.

### File schema

```markdown
# <Pretty Name>

**Blocked:** YYYY-MM-DD
**Exit code:** <a | b | f | j | reject>
**Reason:** one-line summary

| Field | Value |
|---|---|
| Homepage | <url or "—"> |
| Upstream repo | <url or "—"> |
| License | <name> (<class>) |
| Image | <image>:<tag>  (or "none" for exit a) |
| Description | <description_short> |
| Paid | true / false |
| Auth-proxy | supported / not supported / unknown |

## Reason for block

Multi-sentence explanation citing the exit criterion and the specific
evidence (license text URL, missing image output, paid tier requirement).

## Research notes

Verbatim or trimmed copy of `.add-app-scratch/research_notes.md` — keep
auth-proxy, telemetry, deployment-quirk findings so a future reconsider
does not redo the research from scratch.
```

### Procedure on hard exit

1. Render the schema above using `research.json` and `research_notes.md`
   from scratch. Use today's date for `Blocked:`.
2. Write the file to `blocked_apps/<name>.md`.
3. `git add blocked_apps/<name>.md` and commit:
   `docs(blocked_apps): record <name> — exit <code>`.
4. Push the branch and open a non-draft PR titled
   `Document blocked app: <pretty_name>` with the body summarising the
   exit reason. Do not include `apps/<name>/` changes.
5. Leave the worktree in place so the user can inspect scratch files.

If `blocked_apps/<name>.md` already exists (re-run of a previously
blocked app), update it in place rather than creating a duplicate, and
adjust the `Blocked:` date if the exit reason changed.

## Scaffold checklist

Before opening a PR, verify all of the following:

- [ ] `apps/<name>/app_meta.json` exists and is valid JSON.
- [ ] `apps/<name>/docker-compose.yml.template` exists.
- [ ] `apps/<name>/update_check.py` exists and either returns a parseable dict when `check('')` is called, or raises `NotImplementedError` as a documented stub.
- [ ] `docker manifest inspect` passed for the chosen image and tag.
- [ ] `just build-store-data` completed without error.
