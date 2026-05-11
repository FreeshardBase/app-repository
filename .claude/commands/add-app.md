---
description: Add a new app to the Freeshard app repository (or reevaluate an existing one)
argument-hint: <app-name>
---

Invoke the `add-app` skill with the argument `$1` (the app name).

The skill handles everything: research, suitability check, file drafting, worktree, and PR. It will only stop and ask if the research subagent reported ambiguity. Otherwise it runs end-to-end and prints the PR URL.
