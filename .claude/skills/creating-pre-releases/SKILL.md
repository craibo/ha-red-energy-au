---
name: creating-pre-releases
description: Use when asked to create/cut/publish a pre-release, beta, or GitHub release for this repo, or when the manifest version has been bumped and needs a matching release
---

# Creating Pre-releases

## Overview

Creates a GitHub pre-release tagged with the version from `custom_components/red_energy/manifest.json`, always from `main`. Publishing triggers `.github/workflows/release.yml`, which zips `custom_components/red_energy` and attaches it — this is public and visible to HACS/repo watchers, so confirm before publishing if anything is ambiguous.

## Procedure

1. **Read the version.** `grep '"version"' custom_components/red_energy/manifest.json`. This is the tag — don't invent or bump a version here; that happens in the PR that changes the manifest.

2. **Confirm you're on `main`.** Never release from a feature branch. `git branch --show-current`; if not `main`, `git checkout main && git pull` or abort and explain why. Re-check the manifest version after switching — a branch's version may not be merged yet.

3. **Check for duplicates before creating anything:**
   - `git tag -l | grep -x "<version>"` (and `git ls-remote --tags origin | grep "<version>"` if unsure)
   - `gh release view <version>` — must fail with "release not found"

   If either already exists, stop and ask the user how to proceed instead of continuing. Don't skip this because "the version was just bumped" — the manifest can lag what's already tagged, especially right after a merged PR.

4. **Create the release:**
   ```bash
   gh release create <version> --target main --prerelease --generate-notes --title "<version>"
   ```
   `--generate-notes` pulls GitHub's auto-changelog from merged PRs — don't hand-write notes unless asked.

5. **Verify the workflow actually produced the artifact:**
   ```bash
   gh run list --workflow=release.yml --limit 3
   ```
   Confirm the run for your tag is `completed` / `success`. A failed run means the release exists with no attached zip — investigate before reporting done.

6. **Report the release URL** (`https://github.com/<owner>/<repo>/releases/tag/<version>`) — GitHub URLs aren't sensitive, always link them.

## Common mistakes

- **Skipping the branch check** — releasing from a feature branch ships unmerged code as if it were `main`.
- **Skipping the duplicate check** — `gh release create` fails cleanly on a duplicate tag (`422 Release.tag_name already exists`, no side effects), but checking first lets you explain the situation instead of surfacing a raw API error.
- **Forgetting `--target main`** — without it, the release tags whatever ref is currently checked out.
- **Hand-writing release notes by default** — this repo's convention is `--generate-notes`.
- **Omitting `--prerelease`** — this repo has never published a non-pre-release from this workflow in recent history; always pass it unless the user explicitly asks for a full release.
