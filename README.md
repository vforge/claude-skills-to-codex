# Claude Skills to Codex

Codex plugin that makes Claude Code skills available in Codex.

## Behavior

- A `SessionStart` hook scans `~/.claude/skills/` and project `.claude/skills/` directories.
- It injects a compact metadata index into the new Codex session and keeps full skill files at their original paths.
- Project-local skills override global skills with the same name.
- `/reload-skills` rescans the same locations during an active session.
- The hook writes a best-effort metadata cache to `PLUGIN_DATA/claude-skills.json`.

The bridge deliberately does not copy skill files or execute their contents automatically. Codex reads a full `SKILL.md` only when that skill is relevant to the current task.

## Install

### Install with Codex CLI

Add this repository's marketplace and install the plugin:

```bash
codex plugin marketplace add vforge/claude-skills-to-codex
codex plugin add claude-skills-to-codex@claude-skills-to-codex
codex plugin list
```

You do not need to create a personal marketplace, edit a JSON file, clone the repository, or create a symlink. Codex downloads the plugin from GitHub into its local plugin cache. Start a new Codex session after installation and approve the hook if Codex prompts you. Use `/reload-skills` after Claude Code skills change.

To update the plugin, run:

```bash
codex plugin marketplace upgrade claude-skills-to-codex
```

To publish an update, bump `version` in `.codex-plugin/plugin.json` and push the change to GitHub. This marketplace follows the repository's default branch.

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
