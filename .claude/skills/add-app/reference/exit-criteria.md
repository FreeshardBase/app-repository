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
