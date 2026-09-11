# Claude Skills to Codex

Local Codex plugin that bridges Claude Code skills into Codex.

## Behavior

- A `SessionStart` hook scans `~/.claude/skills/` and project `.claude/skills/` directories.
- It injects a compact metadata index into the new Codex session and keeps full skill files at their original paths.
- Project-local skills override global skills with the same name.
- `/reload-skills` rescans the same locations during an active session.
- The hook writes a best-effort metadata cache to `PLUGIN_DATA/claude-skills.json`.

The bridge deliberately does not copy skill files or execute their contents automatically. Codex reads a full `SKILL.md` only when that skill is relevant to the current task.

## Local test

From this plugin directory:

```bash
python3 scripts/load_claude_skills.py --cwd "$PWD"
python3 scripts/load_claude_skills.py --cwd "$PWD" --json
```

To test the hook protocol:

```bash
printf '%s\n' '{"hook_event_name":"SessionStart","cwd":"'"$PWD"'"}' | python3 scripts/load_claude_skills.py --hook
```

Install or enable the plugin in Codex, trust its hook when prompted, then start a new session. Use `/reload-skills` after changing Claude Code skills.
