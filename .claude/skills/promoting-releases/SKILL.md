---
name: promoting-releases
description: Use when asked to promote/upgrade a pre-release to a full/latest release, mark a pre-release as stable, or graduate a beta release for this repo
---

# Promoting a Pre-release to Latest

## Overview

Flips an existing GitHub pre-release to a full release and makes it "Latest", rewriting its release notes to cover every change since the **previous full (non-prerelease) release** — not just since the immediately preceding tag, which is usually another pre-release. Also surfaces any warnings (breaking changes, required migrations, manual steps) at the top of the notes.

This only edits an existing release object. It does **not** create a new tag, does **not** re-run `.github/workflows/release.yml` (that workflow triggers on `release: [published]`, which only fires once, at initial creation — editing `prerelease`/`make_latest` afterward is silent), and does **not** touch the already-uploaded `red_energy.zip` asset. If no code changed between the pre-release and now, the existing asset is still correct.

## Procedure

1. **List current pre-releases and confirm which one to promote.**
   ```bash
   gh release list --repo <owner>/<repo> --json tagName,isPrerelease,publishedAt \
     --jq '.[] | select(.isPrerelease) | "\(.tagName)\t\(.publishedAt)"'
   ```
   Always ask the user to confirm the exact version, even if only one pre-release exists or one seems obviously implied — never guess. Do not proceed until they name it explicitly.

2. **Confirm the target actually exists and is a pre-release.**
   ```bash
   gh release view <version> --repo <owner>/<repo> --json tagName,isPrerelease,isDraft
   ```
   If `isPrerelease` is already `false`, stop and tell the user it's already a full release rather than proceeding.

3. **Find the previous *full* release — not the previous tag.** This must be done *before* promoting, since `releases/latest` excludes pre-releases and will otherwise just re-resolve to the version being promoted.
   ```bash
   gh api repos/<owner>/<repo>/releases/latest --jq '.tag_name'
   ```
   This is the correct baseline for the changelog — it may be several versions back if multiple pre-releases shipped in between (e.g. promoting `1.14.3` when `1.14.0` was the last full release should include everything from `1.14.1`, `1.14.2`, and `1.14.3`, not just `1.14.3`'s own commits).

   If `releases/latest` 404s (no full release exists yet), ask the user what baseline to use instead of guessing.

4. **Generate the changelog against that explicit baseline.** Do NOT use `gh release create --generate-notes` or call `generate-notes` without `previous_tag_name` — both default to the immediately preceding tag (usually the prior pre-release), which undercounts everything already shipped in earlier pre-releases.
   ```bash
   gh api repos/<owner>/<repo>/releases/generate-notes \
     -f tag_name=<version> \
     -f target_commitish=main \
     -f previous_tag_name=<previous-full-release> \
     --jq '.body'
   ```

5. **Scan the same range for anything warning-worthy**, then check the commits/PRs actually in range:
   ```bash
   git log --oneline <previous-full-release>..<version>
   gh pr list --repo <owner>/<repo> --state merged --search "<previous-full-release>..<version>" 2>/dev/null
   ```
   Look for:
   - A manifest **MAJOR** version bump (`grep '"version"' custom_components/red_energy/manifest.json` at each boundary) — HA custom integration major bumps often mean breaking config/entity changes
   - Commit/PR titles or bodies containing "breaking", "migration", "manual step", "remove", "rename" in a way that affects existing users' entities/config (e.g. a sensor rename that changes `unique_id`, a required re-auth, a config entry migration)
   - Anything in `config_migration.py` version-gate changes within the range

   Only include a warning if there's a concrete reason — don't invent generic caution text. If nothing warrants a warning, omit the section entirely rather than padding it.

6. **Compose the final release body**: if warnings were found, prepend a `## ⚠️ Warnings` section (bulleted, specific, linking the relevant PR) above the generated `## What's Changed` notes. Otherwise use the generated notes unchanged.

7. **Show the user the composed notes and the promotion plan (from version → to "Latest", baseline used) and get explicit confirmation before writing anything** — this changes what HACS/watchers see as the recommended install target for everyone, which is harder to walk back cleanly than creating a new pre-release.

8. **Apply the promotion**:
   ```bash
   gh release edit <version> --repo <owner>/<repo> --prerelease=false --latest --notes-file <file>
   ```
   Use `--notes-file` (write the composed body to a temp file first) rather than `--notes` inline — release notes are multi-paragraph markdown and shell-quoting them inline is error-prone.

9. **Verify**:
   ```bash
   gh release view <version> --repo <owner>/<repo> --json isPrerelease,tagName
   gh api repos/<owner>/<repo>/releases/latest --jq '.tag_name'
   ```
   Confirm `isPrerelease` is now `false` and `releases/latest` now resolves to `<version>`.

10. **Report the release URL** (`https://github.com/<owner>/<repo>/releases/tag/<version>`) and summarize what changed — GitHub URLs aren't sensitive, always link them.

## Common mistakes

- **Trusting `--generate-notes`'s default baseline** — it diffs against the immediately preceding tag, which is almost always a pre-release, not the last full release. This silently drops changes from earlier pre-releases in the same cycle.
- **Resolving "previous full release" after promoting** — once the target is promoted, `releases/latest` returns the target itself. Always capture the baseline in step 3, before step 8.
- **Assuming edit re-triggers the release workflow** — it doesn't; the zip asset from initial publish is reused as-is. If code changed on `main` after the pre-release was cut, flag this to the user, since the attached zip would be stale relative to `main`.
- **Padding notes with a generic "please backup before upgrading" warning on every promotion** — only warn when the actual diff contains something concrete (a real breaking change, migration, or manual step). Empty caution boilerplate trains users to ignore warnings.
- **Guessing which pre-release the user means** — always list and confirm explicitly, even when only one exists.
