default:
  just --list

new-app name:
    cp -r inactive_apps/template apps/{{name}}
    sed -i "s/<<name>>/{{name}}/g" apps/{{name}}/*

build-store-data:
    python -m build_store_data

update-check:
    python3 update/update.py check

update-apply app version branch_ts mode reason="":
    python3 update/update.py apply {{app}} {{version}} --{{mode}} --branch-ts {{branch_ts}} --reason "{{reason}}"
