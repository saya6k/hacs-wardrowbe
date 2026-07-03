---
name: hacs-preflight
description: Run the pre-PR sanity checks for this HACS custom integration — Python compile, JSON validity, manifest/hacs.json required keys, strings/translations parity, brand assets, and the HACS + hassfest validations. Use before committing or opening a PR.
---

# HACS preflight checks

Run the baseline below and report pass/fail per check with real output. The
authoritative requirements are in `.github/copilot-instructions.md` and
<https://www.hacs.xyz/docs/publish/integration/>.

## Baseline

1. **Python compiles:** `python3 -m compileall -q custom_components/<domain>`.
2. **JSON valid:** every `manifest.json`, `hacs.json`, `strings.json`,
   `translations/*.json` loads with `python3 -c "import json; json.load(...)"`.
3. **manifest.json required keys** (HACS): `domain`, `name`, `version`,
   `documentation`, `issue_tracker`, `codeowners`. And
   `domain` == the `custom_components/<dir>` name == `const.DOMAIN`.
4. **Semver:** `manifest.json` `version` matches `^\d+\.\d+\.\d+$`. It is bumped
   by release-drafter's `sync-manifest-version` job from the resolved draft
   version — never by hand.
5. **i18n parity:** the key tree of `strings.json`, `translations/en.json`, and
   `translations/ko.json` is identical (only values differ).
6. **Brand asset:** `custom_components/<domain>/brand/icon.png` exists (HACS
   requires brand assets; a `logo.png` is recommended).
7. **Hygiene:** LF line endings, no leftover `{{TOKENS}}`.

## Validation (CI repeats these on every push/PR via `.github/workflows/validate.yml`)

- **HACS:** `hacs/action@main` with `category: integration`.
- **hassfest:** `home-assistant/actions/hassfest`.
- Run locally only if you have the HA dev container; otherwise rely on CI and
  mark these SKIPPED.

## IMPORTANT

- Report each check as `OK` / `FAIL` (+ first error) / `SKIPPED` (+ why). Do not
  claim a skipped check passed.
- Do not fix unrelated findings here — just run and report.

## Output

- One line per check, then an overall **ready / not ready for PR** verdict.
