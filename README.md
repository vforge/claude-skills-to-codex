# Claude Skills to Codex

Local Codex plugin that bridges Claude Code skills into Codex.

## Behavior

- A `SessionStart` hook scans `~/.claude/skills/` and project `.claude/skills/` directories.
- It injects a compact metadata index into the new Codex session and keeps full skill files at their original paths.
- Project-local skills override global skills with the same name.
- `/reload-skills` rescans the same locations during an active session.
- The hook writes a best-effort metadata cache to `PLUGIN_DATA/claude-skills.json`.

The bridge deliberately does not copy skill files or execute their contents automatically. Codex reads a full `SKILL.md` only when that skill is relevant to the current task.

## Install

### Codex CLI

Clone the repository and expose it through the personal plugin marketplace:

```bash
git clone https://github.com/vforge/claude-skills-to-codex.git \
  ~/Developer/vforge/claude-skills-to-codex

mkdir -p ~/plugins
ln -sfn ~/Developer/vforge/claude-skills-to-codex \
  ~/plugins/claude-skills-to-codex
```

Add the following plugin entry to `~/.agents/plugins/marketplace.json`, preserving any existing entries:

```json
{
  "name": "claude-skills-to-codex",
  "source": {
    "source": "local",
    "path": "./plugins/claude-skills-to-codex"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Install it from the personal marketplace:

```bash
codex plugin add claude-skills-to-codex@personal
```

Start a new Codex session after installation, approve the hook if prompted, and use `/reload-skills` whenever Claude Code skills change.

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
