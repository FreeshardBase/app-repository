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
            diff_text, nontrivial = compose_diff(old_yaml, new_yaml, current, latest)
            if nontrivial:
                reasons.append("upstream compose changed beyond the app version (supporting image or structure)")
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
    from update.update_lib import OptOut

    try:
        current = _current_version(app_dir)
    except (FileNotFoundError, KeyError, ValueError) as e:
        # apps/ should only contain valid app directories. A dir without a
        # readable app_meta.json is a stray (e.g. an orphaned __pycache__ left
        # by a removed app). Surface it as an error for the agent to clean up
        # rather than crashing the whole check run.
        return {
            "app": app_dir.name, "current": None, "status": "error",
            "error": f"not a valid app directory: cannot read app_meta.json ({type(e).__name__}: {e})",
        }
    mod = _load_app_check(app_dir)
    if mod is None:
        return {"app": app_dir.name, "current": current, "status": "no_script"}
    try:
        payload = mod.check(current)
    except OptOut as e:
        return {"app": app_dir.name, "current": current, "status": "opt_out", "reason": str(e)}
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
        elif s == "opt_out":
            print(f"  OPT_OUT   {name:<25} {e.get('reason','')}")
        elif s == "no_script":
            print(f"  NO_SCRIPT {name:<25}")


FILE_EXTENSIONS = ("yml.template", "json", "env")


def _replace_in_files(app_dir: Path, old: str, new: str) -> None:
    """Replace `old` with `new` across the app's template/json/env files."""
    for ext in FILE_EXTENSIONS:
        for fp in app_dir.rglob(f"*.{ext}"):
            txt = fp.read_text()
            if old in txt:
                fp.write_text(txt.replace(old, new))


def _docker_pull_test(app_dir: Path) -> bool:
    """Render the compose template with sandbox paths, attempt pull dry-run."""
    src = app_dir / "docker-compose.yml.template"
    dst = app_dir / "docker-compose.yml"
    rendered = src.read_text().replace("{{ fs.app_data }}", "./app_data").replace("{{ fs.shared }}", "./shared")
    dst.write_text(rendered)
    try:
        r = subprocess.run(
            ["docker", "compose", "pull", "--dry-run", "-q"],
            cwd=app_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        return r.returncode == 0
    finally:
        dst.unlink()


def _ensure_branch(branch: str) -> None:
    """Switch to `branch`; create if missing."""
    cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
    if cur == branch:
        return
    exists = subprocess.run(["git", "rev-parse", "--verify", branch], capture_output=True).returncode == 0
    if exists:
        subprocess.run(["git", "checkout", branch], check=True)
    else:
        subprocess.run(["git", "checkout", "-b", branch], check=True)


def cmd_apply(args):
    app = args.app
    new_version = args.version
    mode = "AUTO" if args.auto else "REVIEW"
    branch = f"updates/{args.branch_ts}"

    app_dir = APPS_DIR / app
    if not app_dir.is_dir():
        sys.exit(f"unknown app: {app}")

    current = _current_version(app_dir)
    if current == new_version:
        print(f"{app}: already at {new_version}, skipping")
        return

    _ensure_branch(branch)
    _replace_in_files(app_dir, current, new_version)

    if not _docker_pull_test(app_dir):
        subprocess.run(["git", "checkout", "--", f"apps/{app}"])
        sys.exit(f"{app}: docker pull --dry-run failed; aborted, no commit")

    # Look up release notes URL from the latest check report, if present.
    notes_url = ""
    if LATEST_CHECK_JSON.exists():
        rep = json.loads(LATEST_CHECK_JSON.read_text())
        notes_url = rep.get("apps", {}).get(app, {}).get("release_notes_url") or ""

    subprocess.run(["git", "add", f"apps/{app}"], check=True)
    msg_lines = [f"update {app} from {current} to {new_version} [{mode}]", ""]
    if notes_url:
        msg_lines.append(notes_url)
    if mode == "REVIEW" and args.reason:
        msg_lines.append(args.reason)
    subprocess.run(["git", "commit", "-m", "\n".join(msg_lines)], check=True)
    print(f"committed {app} {current} -> {new_version} [{mode}]")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("apply")
    a.add_argument("app")
    a.add_argument("version")
    a.add_argument("--branch-ts", required=True, help="iso timestamp for branch name, YYYY-MM-DDTHH-MM-SSZ")
    grp = a.add_mutually_exclusive_group(required=True)
    grp.add_argument("--auto", action="store_true")
    grp.add_argument("--review", action="store_true")
    a.add_argument("--reason", default="")
    a.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
