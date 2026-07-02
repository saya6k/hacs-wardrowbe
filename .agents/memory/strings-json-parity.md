---
name: strings-json-parity
description: strings.json must stay in sync with translations/en.json — hacs-preflight catches drift
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e88bf81a-82e3-4de3-908b-02dd0b289b76
---

When adding a new entity, service, or translatable key: update BOTH `custom_components/wardrowbe/strings.json` AND `custom_components/wardrowbe/translations/en.json` (and `ko.json` if it exists).

**Why:** `hacs-preflight` checks that the key trees of `strings.json`, `translations/en.json`, and `translations/ko.json` are identical. Drift (e.g., adding a key to en.json but not strings.json) fails the check.

**How to apply:** After adding any translation key, run the hacs-preflight i18n parity check or compare key trees with a script. In this session, `get_summary` service keys were in en.json/ko.json but missing from strings.json — CI would have caught it, but it's better caught locally.
