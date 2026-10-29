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

### Install from GitHub with Codex CLI

Add the plugin to your personal marketplace in `~/.agents/plugins/marketplace.json`. Create the file if it does not exist. If it already exists, add the plugin object to its `plugins` array and keep the other entries.

```bash
mkdir -p ~/.agents/plugins
```

Use this complete example for a new marketplace file:

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
  },
  "plugins": [
    {
      "name": "claude-skills-to-codex",
      "source": {
        "source": "url",
        "url": "https://github.com/vforge/claude-skills-to-codex.git"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Install and verify the plugin:

```bash
codex plugin add claude-skills-to-codex@personal
codex plugin list
```

Codex downloads the plugin from GitHub into its local plugin cache. You do not need to clone this repository or create a symlink. Start a new Codex session after installation and approve the hook if Codex prompts you. Use `/reload-skills` after Claude Code skills change.

To publish an update, bump `version` in `.codex-plugin/plugin.json` and push the change to GitHub. The marketplace entry above follows the repository's default branch. To install the new version, remove and reinstall the plugin:

```bash
codex plugin remove claude-skills-to-codex@personal
codex plugin add claude-skills-to-codex@personal
```

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
