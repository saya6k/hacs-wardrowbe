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
3. **Conventional Commit** — title format `fix(scope): description` for release-please. Never `--no-verify`
4. **Push + `gh pr create`** — PR title must be valid Conventional Commit (squash merge uses it as the commit on main)
5. **Never bump `manifest.json` version** — release-please owns versioning

After merge: `git switch main && git pull --ff-only`. Release PR will auto-bump version + CHANGELOG.
