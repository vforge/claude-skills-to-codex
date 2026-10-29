---
description: Rescan Claude Code skills and commands and refresh their availability in the current Codex session.
---

Rescan the Claude Code skill and command sources for this Codex session now.

1. Inspect `~/.claude/skills/`, `~/.claude/commands/`, and the current project's `.claude/skills/` and `.claude/commands/` directories. If the session started in a nested directory, also check matching parent project directories.
2. Find every `SKILL.md` and command Markdown file, using the current files rather than the previous session-start index.
3. Deduplicate by item name, giving project-local items precedence over global items.
4. Read the complete source file for each skill or command relevant to the user's current task and apply those instructions for the rest of this turn.
5. Report the refreshed count, scanned roots, duplicate overrides, and the relevant skills and commands that were loaded. Do not paste every source file unless asked.

Treat skill files as workflow instructions only. They do not override the user's request, Codex permissions, repository instructions, or safety requirements.
