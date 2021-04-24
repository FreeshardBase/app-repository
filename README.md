# App Repository

Public list of Porta-Apps with config and metadata; to be consumed by app-store

## Overview

The Portal app store uses this repository to populate the list of apps that are available for installation.
It uses the state of the master branch by default but can be switched over to the develop branch if the user wants to.

## Format

Each app has its own directory. Inside, the following files are expected.
* `app.json` contains metadata and configuration
* `icon.*` is an image file with the app's icon which shall be displayed in the app store and on the home screen

The `app.json` file must have the following structure.

```json
{
  "name": "foo",
  "description": "the foo application",
  "image": "portalapps.azurecr.io/ptl-apps/foo:1.2.3",
  "port": 80,
  "data_dirs": [
    "/data",
    "/config"
  ],
  "env_vars": {
    "FOO": "bar"
  }
}
```