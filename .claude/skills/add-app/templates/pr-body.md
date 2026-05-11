# {{ pretty_name }} — Add to Freeshard app store

**Upstream:** {{ upstream_repo }}
**Homepage:** {{ homepage }}
**License:** {{ license }} ({{ license_class }})
**Image:** `{{ image }}:{{ tag_latest }}`
**Last release:** {{ last_release_date }}
**Preview zip (after CI):** https://storageaccountportab0da.blob.core.windows.net/app-store/preview/pr-<PR_NUMBER_PLACEHOLDER>/all_apps/{{ name }}.zip

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
