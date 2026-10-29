# Claude Skills to Codex

Codex plugin that makes Claude Code skills and commands available in Codex.

## Behavior

- A `SessionStart` hook scans `~/.claude/skills/` and `~/.claude/commands/`, plus matching project `.claude/skills/` and `.claude/commands/` directories.
- It injects a compact metadata index into the new Codex session and keeps full skill files at their original paths.
- Project-local skills and commands override global items with the same name.
- The `reload-skills` skill rescans the same locations during an active session. In Codex, invoke it from the `$` skill menu; plugin skills are namespaced by plugin.
- The hook writes a best-effort metadata cache to `PLUGIN_DATA/claude-skills.json`.

The bridge leaves source files in place and creates small native Codex skill wrappers so imported items appear in Codex's skill catalog. Codex reads the full source only when that item is relevant to the current task.

## Install

### Install with Codex CLI

Add this repository's marketplace and install the plugin:

```bash
codex plugin marketplace add vforge/claude-skills-to-codex
codex plugin add claude-skills-to-codex@claude-skills-to-codex
codex plugin list
```

You do not need to create a personal marketplace, edit a JSON file, clone the repository, or create a symlink. Codex downloads the plugin from GitHub into its local plugin cache. Start a new Codex session after installation and approve the hook if Codex prompts you. Use the `reload-skills` skill or start a new session after Claude Code skills or commands change.

To update the plugin, run:

```bash
codex plugin marketplace upgrade claude-skills-to-codex
```

To publish an update, bump `version` in `.codex-plugin/plugin.json` and push the change to GitHub. This marketplace follows the repository's default branch.

## Local test

From this plugin directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

These smoke tests run the loader with temporary Claude skill and command roots, plugin directories, and cache paths. They verify recursive discovery, project precedence, generated Codex skill wrappers in the Codex user skill root, and stale-wrapper cleanup without touching the installed plugin or your live skill directories. When the Codex CLI is available, they also install the plugin into a temporary Codex home and query the app-server `skills/list` catalog used by the skill menus to confirm nested `skill1` and `command1` are indexed while the plugin is enabled. This does not open or interact with the current Codex UI session.

To inspect the discovered metadata manually:

```bash
python3 scripts/load_claude_skills.py --cwd "$PWD"
python3 scripts/load_claude_skills.py --cwd "$PWD" --json
```

To test the hook protocol:

```bash
printf '%s\n' '{"hook_event_name":"SessionStart","cwd":"'"$PWD"'"}' | python3 scripts/load_claude_skills.py --hook
```

Install or enable the plugin in Codex, trust its hook when prompted, then start a new session. Use the `reload-skills` skill after changing Claude Code skills or commands.
