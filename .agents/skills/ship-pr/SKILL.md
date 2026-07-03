---
name: ship-pr
description: Drive this HACS integration's commit → push → PR → merge flow so release-drafter's rolling draft and manifest-sync stay accurate. Use when shipping a change as a pull request — it enforces branch-first, Conventional-Commit titles, and the right merge method.
---

# Ship a change (commit → push → PR → merge)

release-drafter labels each merged PR from its title to compute the next
version for a single rolling draft release. A malformed commit/PR title still
gets labeled `chore` (patch) by the fallback, but won't land in the right
changelog section. Defer to [[conventional-commit]] for wording and
[[hacs-preflight]] for sanity checks.

## 1. Branch

- **Never commit on `main`.** `git switch -c <type>/<short-slug>`
  (e.g. `feat/add-rain-sensor`, `fix/auth-retry`).

## 2. Pre-PR checks

- Run [[hacs-preflight]] (Python compile, JSON, manifest keys, i18n parity,
  brand asset). CI repeats HACS + hassfest but does not replace local checks.

## 3. Commit

- Use [[conventional-commit]]. **Never** `--no-verify` / `--no-gpg-sign`.
- Don't hand-bump `manifest.json` `version` — release-drafter's CI-pushed sync
  commit owns it.

## 4. Push & open PR

- `git push -u origin <branch>`.
- `gh pr create` — the **PR title MUST be a valid Conventional Commit**. On a
  squash merge the title becomes the commit on `main` that release-drafter's
  autolabeler reads.

## 5. Merge

- This is a **single package**, so a **squash merge is fine** — the PR title is
  the one release-relevant commit. (No multi-scope rebase concern as in
  `ha-apps`.)
- After merge, there is no release PR to review: release-drafter updates its
  one rolling draft release directly, and a separate bot commit
  (`chore(release): sync manifest.json version to X.Y.Z [skip ci]`) lands on
  `main` moments later.

## 6. After merge

- `git switch main && git pull --ff-only origin main` — twice if you're quick,
  since the manifest-sync bot commit typically lands a few seconds after your
  merge and won't be present on the first pull.
- The version is **not** tagged or published yet at this point — a maintainer
  must manually click **Publish** on the draft release in the GitHub UI
  (`https://github.com/saya6k/ha-wardrowbe/releases`) for a real tag + GitHub
  Release to exist and for `docs.yml` (which triggers on `release: published`)
  to deploy the docs site. Until then, `manifest.json` on `main` may show a
  version with no corresponding tag — expected.

## IMPORTANT

- Set the repo's **Pages source to "GitHub Actions"** once, so the Docs
  workflow can publish the Zensical site.
