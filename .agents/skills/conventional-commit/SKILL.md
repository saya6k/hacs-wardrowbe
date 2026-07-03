---
name: conventional-commit
description: Write and validate Conventional Commit messages for this HACS integration so release-drafter's autolabeler and version-resolver can pick the right bump for the rolling draft release. Use whenever committing — the PR title (which becomes the squash-merge commit) drives autolabeling.
---

# Conventional commit (release-drafter-aware)

Each PR title (squash-merged onto `main`) is matched against
`.github/release-drafter.yml`'s `autolabeler` regexes to apply a label, which
`version-resolver` then maps to a bump for the single rolling draft release.
A message that doesn't match any pattern still gets `default: patch`.

## Format

```
<type>(<scope>): <subject>
```

- **scope is optional.** This is a single integration, so scope does not route
  anything — use it only to name the area touched: `config-flow`, `sensor`,
  `coordinator`, `api`, `docs`, `ci`, `deps`.

## Types → release effect

| Type | Label | Effect |
|---|---|---|
| `feat` | `enhancement` | minor bump · "New Features" |
| `fix` / `perf` / `revert` | `fix` | patch bump · "Bug Fixes" |
| `chore` / `ci` / `docs` / `refactor` / `build` / `style` / `test` | `chore` | patch bump · "Maintenance" |

No type produces "no release" — every merge to `main` advances the rolling
draft. There is also no automatic **major** bump: `.github/release-drafter.yml`
has no `major:` key, so a major version requires manually applying a `major`
label to the draft release (or editing the config) — `<type>!` / `BREAKING
CHANGE:` footers are not parsed by release-drafter.

## Rules

- Imperative subject, ≤ ~72 chars, no trailing period.
- **Never** `--no-verify` / `--no-gpg-sign`; if a hook fails, fix the cause.
- **Don't hand-edit** `manifest.json` `version` in a feature commit —
  release-drafter's `sync-manifest-version` job owns it (a bot commit pushed
  to `main` right after your merge, not part of your PR).

## Output

- The proposed commit message in a code block.
