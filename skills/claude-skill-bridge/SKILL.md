---
name: claude-skill-bridge
description: Discover and apply Claude Code skills and commands from global or project .claude directories.
---

# Claude Code skill bridge

This plugin makes Claude Code skills and commands available to Codex while leaving their source files in place. A session-start hook scans:

- `~/.claude/skills/`
- `~/.claude/commands/`
- project `.claude/skills/` and `.claude/commands/` directories, including matching parent project roots when Codex starts in a subdirectory

The hook adds an index to the session context. The index is metadata-only so a large personal skill collection does not consume the whole context window.

Imported skills and commands appear as native Codex skills. Each generated wrapper points to the original source file, which Codex reads only when that item is relevant.

## Applying a Claude Code skill or command

When the task matches a discovered skill or command:

1. Read the complete source file from the path in the bridge index.
2. Follow its workflow and references for the current task.
3. Prefer project-local items over global items when names collide.
4. Continue to follow Codex permissions, repository instructions, and user instructions. A Claude Code skill cannot grant new permissions or authorize unrelated actions.

If the session-start index is missing or stale, use the `reload-skills` skill from the `$` menu to rescan the current working directory and refresh the available-skill metadata.
