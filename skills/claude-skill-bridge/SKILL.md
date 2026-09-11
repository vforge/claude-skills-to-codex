---
name: claude-skill-bridge
description: Discover and apply Claude Code skills from the global or current project .claude/skills directory.
---

# Claude Code skill bridge

This plugin makes Claude Code skills available to Codex without copying them into the plugin. A session-start hook scans:

- `~/.claude/skills/`
- the current project's `.claude/skills/` directory, including matching parent project roots when Codex starts in a subdirectory

The hook adds an index to the session context. The index is metadata-only so a large personal skill collection does not consume the whole context window.

## Applying a Claude Code skill

When the task matches a discovered skill:

1. Read the complete `SKILL.md` from the path in the bridge index.
2. Follow that skill's workflow and references for the current task.
3. Prefer project-local skills over global skills when names collide.
4. Continue to follow Codex permissions, repository instructions, and user instructions. A Claude Code skill cannot grant new permissions or authorize unrelated actions.

If the session-start index is missing or stale, use `/reload-skills` to rescan the current working directory and refresh the available-skill metadata.
