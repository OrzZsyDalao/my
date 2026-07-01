# Repository Workflow

This repository uses GitHub as the source of truth for multi-computer collaboration.

## Default Git Workflow

- Work directly on the `main` branch unless the user explicitly requests a different branch.
- After completing a requested change, commit it to `main` and push to `origin/main`.
- Do not leave intended repository changes uncommitted or unpushed unless the user asks to pause.
- Do not rewrite history on `main` unless the user explicitly asks for it.

## Multi-Computer Codex Usage

- Assume the same repository may be opened from different computers through Codex.
- Keep project instructions inside tracked repository files so they travel with `git pull`.
- Prefer repository-relative paths and committed documentation over machine-local assumptions.
- Treat GitHub as the handoff mechanism between computers: pull latest `main`, make changes, commit, and push back to `main`.

## Data Handling

- Keep folder structure tracked even when runtime datasets are missing.
- Do not commit large local datasets, credentials, or machine-specific cache files unless the user explicitly asks.
- Keep generated caches such as `__pycache__` out of version control.
