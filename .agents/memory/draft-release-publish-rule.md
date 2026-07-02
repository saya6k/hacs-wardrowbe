---
name: draft-release-publish-rule
description: release-please draft mode — publish each draft before merging the next release PR; Pages env needs the tag policy
metadata: 
  node_type: memory
  type: project
  originSessionId: edc45b43-ac2c-4121-9641-f661d88cfda5
---

ha-wardrowbe uses release-please in **draft mode** (`"draft": true` in
`.github/release-please-config.json`): merging a release PR bumps
`manifest.json` + `CHANGELOG.md` and creates the GitHub release as a **draft**;
a maintainer publishes it manually. Docs deploy via `docs.yml` on
`release: published`.

**Why:** release-please anchors "what's already released" on **git tags**, but a
draft release does **not** create its tag until published. Merging the next
release PR while the previous release is still a draft makes release-please
re-scan from the last *published* tag, re-count old commits (a stale `feat`
forces a wrong minor bump) and duplicate changelog entries. This happened: an
unpublished 0.2.1 draft made release-please propose 0.3.0 with duplicates.

**How to apply:**
- Publish each draft (creates its tag) **before** merging the next release PR.
  Recovery for an inflated PR: publish the stale draft
  (`gh release edit <tag> --draft=false`), then re-run release-please
  (`gh workflow run ci.yml --ref main`) — the PR recomputes correctly.
- `gh release edit --draft=false` **does** fire `release: published` (verified
  on 0.2.2 — Docs ran from the event). The one no-fire case (0.2.1) was
  seconds after `docs.yml`'s trigger change landed on main — likely a trigger
  registration race. If Docs doesn't fire, `gh workflow run docs.yml` instead.
- **Expect a bogus next-release PR after every release-PR merge**: the merge
  push runs release-please, which creates the draft but computes the *next* PR
  before the tag exists → an inflated PR (e.g. 0.3.0 re-counting old feats)
  appears in that window. After publishing the draft, a re-run reports
  "0 commits / skipping" but does **not** clean the stale PR — close it
  manually (`gh pr close <n> --delete-branch`); the next real commit
  regenerates a correct one.
- The **github-pages environment** rejects deployments from refs not on its
  allowlist. Release-event runs execute on the **tag**, so the environment
  needs a tag policy: `tag: wardrowbe-v*` (added 2026-07-02 via
  `POST /environments/github-pages/deployment-branch-policies`). Without it the
  job fails before any step with "Tag ... not allowed to deploy".

See also [[ship-pr-workflow]].
