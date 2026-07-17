---
name: ship-pr-workflow
description: PR workflow — branch → hacs-preflight → conventional-commit → push → gh pr create
metadata: 
  node_type: memory
  type: project
  originSessionId: e88bf81a-82e3-4de3-908b-02dd0b289b76
---

Shipping a change follows `/ship-pr` which enforces:

1. **Branch off main** — `git switch -c <type>/<short-slug>` (e.g. `fix/service-validation-error-guard`)
2. **HACS preflight** — Python compile, JSON validity, manifest keys, semver, i18n parity, brand asset
3. **Conventional Commit** — title format `fix(scope): description`; release-drafter's autolabeler reads it. Never `--no-verify`
4. **Push + `gh pr create`** — PR title must be valid Conventional Commit (squash merge uses it as the commit on main)
5. **Never bump `manifest.json` version** — it stays committed as `0.0.0` on `main` permanently. `release-zip.yml` patches the version into the *zip asset's* manifest.json at release-publish time (tag → version), which is what HACS actually installs (`hacs.json` sets `zip_release: true`). There is no bot commit back to `main`.

After merge: `git switch main && git pull --ff-only` — one pull is enough, nothing else lands automatically. release-drafter updates its two rolling drafts (`rc` prerelease track + `stable` track) directly on push to main; a maintainer must manually publish each from the GitHub Releases UI (or `gh release edit <tag> --draft=false [--prerelease]`) — no release PR to merge, unlike release-please. Publishing the `rc` draft triggers `release-zip.yml` (attaches the version-patched zip) and, only for a non-prerelease `stable` publish, `docs.yml`.
