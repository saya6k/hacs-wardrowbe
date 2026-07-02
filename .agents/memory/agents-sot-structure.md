---
name: agents-sot-structure
description: Only AGENTS.md + .agents/ are tracked; .claude/.gemini scaffolding is local-only and git clobbers it on cross-boundary checkouts
metadata:
  type: feedback
---

The user's agent-file convention (applied 2026-07-02, PR #16; reference:
~/Projects/ha-apps): **commit the source of truth** — `AGENTS.md` and
`.agents/` (`skills/`, `workflows/`, `agents/`, `memory/`) — **plus
`.claude/settings.json`** (Claude-specific but shared; settings belong in
`.claude/`, not `.agents/`). Everything else is local-only and untracked:
`CLAUDE.md`/`GEMINI.md` → `AGENTS.md` symlinks, `.gemini` → `.agents`,
`.claude/`'s per-item symlinks (`skills`, `commands` → `workflows`, `agents`),
and `.claude/settings.local.json`. Claude's global per-project memory dir
(`~/.claude/projects/<slug>/memory`) symlinks to `<repo>/.agents/memory`.

**Why:** SoT stays tool-agnostic and shared; tool wiring is each developer's
local concern.

**How to apply:**
- When shipping agent-asset changes, stage only `AGENTS.md`/`.agents/**`;
  never `git add` the scaffolding.
- **Gotcha:** the scaffolding is gitignored, so `git checkout` across the
  restructure boundary (or any state where those paths were tracked) silently
  deletes it — this destroyed `.claude/settings.local.json` once
  (unrecoverable; it was never tracked). `settings.json` was recovered via
  `git show <old>:.agents/settings.json`. After such checkouts, recreate:
  `ln -sfn AGENTS.md CLAUDE.md; ln -sfn AGENTS.md GEMINI.md; ln -sfn .agents
  .gemini; mkdir -p .claude; ln -sfn ../.agents/skills .claude/skills;
  ln -sfn ../.agents/workflows .claude/commands; ln -sfn ../.agents/agents
  .claude/agents` and restore settings.
