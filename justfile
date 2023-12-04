default:
  just --list

new-app name:
    cp -r inactive_apps/template apps/{{name}}
    sed -i "s/<<name>>/{{name}}/g" apps/{{name}}/*

build-store-data:
    python -m build_store_data
