#!/usr/bin/env python3
"""Update orchestrator. Two subcommands: check, apply."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"
UPDATE_INFO = REPO_ROOT / "update" / "update_info"
LATEST_CHECK_JSON = UPDATE_INFO / "latest_check.json"

sys.path.insert(0, str(REPO_ROOT))  # so `from update.update_lib import ...` works in app scripts


def _load_app_check(app_dir: Path):
    script = app_dir / "update_check.py"
    if not script.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"update_check_{app_dir.name}", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _current_version(app_dir: Path) -> str:
    meta = json.loads((app_dir / "app_meta.json").read_text())
    return meta["app_version"]


def _classify(app_name: str, current: str, payload: dict) -> dict:
    from update.update_lib import semver_jump, fetch_upstream_compose, compose_diff

    latest = payload["latest_version"]
    if latest == current:
        return {
            "app": app_name, "current": current, "latest": latest,
            "status": "up_to_date", "semver_jump": "patch",
            "release_notes_url": payload.get("release_notes_url"),
            "release_body_snippet": "", "release_body_has_breaking": False,
            "upstream_compose_diff": "", "compose_diff_nontrivial": False,
            "candidate_reasons": [],
        }

    jump = semver_jump(current, latest)
    body = payload.get("release_body") or ""
    snippet = body[:2000]
    breaking = "breaking" in body.lower()
    reasons = []
    if jump == "major":
        reasons.append("major bump")
    if jump == "non_semver":
        reasons.append("non-semver version")
    if breaking:
        reasons.append("'breaking' in release notes")

    diff_text = ""
    nontrivial = False
    url = payload.get("upstream_compose_url")
    if url:
        try:
            old_url = url.replace("{version}", current)
            new_url = url.replace("{version}", latest)
            old_yaml = fetch_upstream_compose(app_name, current, old_url)
            new_yaml = fetch_upstream_compose(app_name, latest, new_url)
            diff_text, nontrivial = compose_diff(old_yaml, new_yaml)
            if nontrivial:
                reasons.append("upstream docker-compose has non-image changes")
        except Exception as e:
            reasons.append(f"compose fetch failed: {e}")

    return {
        "app": app_name, "current": current, "latest": latest,
        "status": "outdated", "semver_jump": jump,
        "release_notes_url": payload.get("release_notes_url"),
        "release_body_snippet": snippet, "release_body_has_breaking": breaking,
        "upstream_compose_diff": diff_text, "compose_diff_nontrivial": nontrivial,
        "candidate_reasons": reasons,
    }


def _check_one(app_dir: Path) -> dict:
    current = _current_version(app_dir)
    mod = _load_app_check(app_dir)
    if mod is None:
        return {"app": app_dir.name, "current": current, "status": "no_script"}
    try:
        payload = mod.check(current)
    except NotImplementedError as e:
        return {"app": app_dir.name, "current": current, "status": "error", "error": str(e)}
    except Exception as e:
        return {"app": app_dir.name, "current": current, "status": "error", "error": repr(e)}
    return _classify(app_dir.name, current, payload)


def cmd_check(args):
    UPDATE_INFO.mkdir(parents=True, exist_ok=True)
    app_dirs = sorted(d for d in APPS_DIR.iterdir() if d.is_dir())
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "apps": {}}

    with ThreadPoolExecutor() as ex:
        futs = {ex.submit(_check_one, d): d for d in app_dirs}
        for fut in as_completed(futs):
            entry = fut.result()
            report["apps"][entry["app"]] = entry

    LATEST_CHECK_JSON.write_text(json.dumps(report, indent=2, sort_keys=True))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_summary(report)


def _print_summary(report: dict):
    print(f"=== Checked {len(report['apps'])} apps at {report['timestamp']} ===")
    for name in sorted(report["apps"]):
        e = report["apps"][name]
        s = e.get("status")
        if s == "outdated":
            r = ", ".join(e.get("candidate_reasons", [])) or "clean"
            print(f"  OUTDATED  {name:<25} {e['current']:<12} -> {e['latest']:<12}  ({r})")
        elif s == "error":
            print(f"  ERROR     {name:<25} {e.get('error','')}")
        elif s == "no_script":
            print(f"  NO_SCRIPT {name:<25}")


def cmd_apply(args):
    raise NotImplementedError("filled in next task")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--json", action="store_true"); c.set_defaults(func=cmd_check)
    a = sub.add_parser("apply"); a.set_defaults(func=cmd_apply)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
