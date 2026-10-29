"""Isolated smoke tests for Claude skill discovery and Codex wrapper generation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "load_claude_skills.py"


class LoadClaudeSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="claude-skills-bridge-")
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.plugin = self.root / "plugin"
        self.codex_home = self.root / "codex-home"
        self.cwd = self.root / "project" / "nested"
        self.global_skills = self.home / ".claude" / "skills"
        self.project_skills = self.root / "project" / ".claude" / "skills"
        (self.plugin / "skills" / "claude-skill-bridge").mkdir(parents=True)
        (self.plugin / "skills" / "claude-skill-bridge" / "SKILL.md").write_text(
            "bridge-owned skill\n", encoding="utf-8"
        )
        self.cwd.mkdir(parents=True)
        self.codex_home.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_skill(self, root: Path, name: str, description: str) -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            f'---\nname: "{name}"\ndescription: "{description}"\n---\n\nInstructions.\n',
            encoding="utf-8",
        )
        return skill_file

    def run_loader(self) -> dict[str, object]:
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(self.home),
                "CODEX_HOME": str(self.codex_home),
                "PLUGIN_DATA": str(self.root / "plugin-data"),
            }
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(self.cwd), "--json"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        return json.loads(result.stdout)

    def test_project_skill_wins_and_wrappers_are_discoverable(self) -> None:
        self.add_skill(self.global_skills, "shared", "global copy")
        self.add_skill(self.global_skills, "global-only", "global skill")
        self.add_skill(self.project_skills, "shared", "project copy")
        self.add_skill(self.project_skills, "project-only", "project skill")

        result = self.run_loader()

        self.assertEqual(result["count"], 3)
        self.assertEqual(result["duplicates"], ["shared"])
        skills = {skill["name"]: skill for skill in result["skills"]}
        self.assertEqual(skills["shared"]["source"], "project")
        self.assertTrue(skills["shared"]["path"].endswith("project/.claude/skills/shared/SKILL.md"))
        for name, skill in skills.items():
            wrapper = self.codex_home / "skills" / "claude-imported" / name / "SKILL.md"
            self.assertTrue(wrapper.is_file(), f"missing Codex wrapper for {name}")
            contents = wrapper.read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", contents)
            self.assertIn(skill["path"], contents)

        self.assertTrue(
            (self.plugin / "skills" / "claude-skill-bridge" / "SKILL.md").is_file(),
            "materialization must preserve the plugin's own bridge skill",
        )
        self.assertFalse((self.plugin / "skills" / "claude-imported").exists())
        cache = json.loads((self.root / "plugin-data" / "claude-skills.json").read_text())
        self.assertEqual(cache["skills"], result["skills"])

    def test_removed_source_skill_removes_stale_wrapper(self) -> None:
        stale = self.add_skill(self.global_skills, "temporary", "temporary skill")
        self.run_loader()
        wrapper = self.codex_home / "skills" / "claude-imported" / "temporary" / "SKILL.md"
        self.assertTrue(wrapper.is_file())

        stale.unlink()
        stale.parent.rmdir()
        result = self.run_loader()

        self.assertEqual(result["count"], 0)
        self.assertFalse(wrapper.exists())
        self.assertTrue(
            (self.plugin / "skills" / "claude-skill-bridge" / "SKILL.md").is_file()
        )

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI is required for app-server discovery")
    def test_installed_plugin_skill_appears_in_codex_catalog(self) -> None:
        repo = SCRIPT.parents[1]
        marketplace_root = self.root / "marketplace"
        source_plugin = marketplace_root / "plugins" / "claude-skills-to-codex"
        shutil.copytree(
            repo,
            source_plugin,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        marketplace = {
            "name": "isolated-bridge-test",
            "plugins": [
                {
                    "name": "claude-skills-to-codex",
                    "source": {
                        "source": "local",
                        "path": "./plugins/claude-skills-to-codex",
                    },
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Productivity",
                }
            ],
        }
        marketplace_file = marketplace_root / ".agents" / "plugins" / "marketplace.json"
        marketplace_file.parent.mkdir(parents=True)
        marketplace_file.write_text(json.dumps(marketplace), encoding="utf-8")

        self.home.mkdir(parents=True)
        codex_home = self.root / "codex-home"
        codex_home.mkdir(exist_ok=True)
        fixture = Path(__file__).resolve().parent / "fixtures" / "nested-project"
        shutil.copytree(fixture, self.cwd, dirs_exist_ok=True)
        environment = os.environ.copy()
        environment.update({"HOME": str(self.home), "CODEX_HOME": str(codex_home)})
        marketplace_add = subprocess.run(
            ["codex", "plugin", "marketplace", "add", str(marketplace_root)],
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(marketplace_add.returncode, 0, marketplace_add.stderr)
        installed = subprocess.run(
            ["codex", "plugin", "add", "claude-skills-to-codex@isolated-bridge-test", "--json"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        installed_path = Path(json.loads(installed.stdout)["installedPath"])
        plugin_state = subprocess.run(
            ["codex", "plugin", "list", "--json"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        registered_plugin = json.loads(plugin_state.stdout)["installed"][0]
        self.assertTrue(registered_plugin["enabled"])

        skill1 = self.cwd / ".claude" / "skills" / "skill1" / "SKILL.md"
        command1 = self.cwd / ".claude" / "commands" / "command1.md"
        def launch_app_server(requests: list[dict[str, object]], expected_id: int) -> dict[str, object]:
            app_server = subprocess.Popen(
                ["codex", "--dangerously-bypass-hook-trust", "app-server", "--stdio"],
                cwd=self.cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert app_server.stdin is not None
            assert app_server.stdout is not None
            response = None
            try:
                app_server.stdin.write("".join(json.dumps(message) + "\n" for message in requests))
                app_server.stdin.flush()
                for line in app_server.stdout:
                    message = json.loads(line)
                    if message.get("id") == expected_id:
                        response = message
                        break
            finally:
                app_server.stdin.close()
                app_server.terminate()
                app_server.wait(timeout=10)
                app_server.stdout.close()
                assert app_server.stderr is not None
                app_server.stderr.close()
            self.assertIsNotNone(response, f"Codex app-server did not answer request {expected_id}")
            self.assertNotIn("error", response)
            return response

        def initialize_messages() -> list[dict[str, object]]:
            return [
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {"clientInfo": {"name": "claude-skills-bridge-test", "version": "1"}},
                },
                {"method": "initialized", "params": {}},
            ]

        # Confirm Codex loaded the installed plugin's SessionStart hook configuration.
        hook_config = launch_app_server(
            initialize_messages() + [{"method": "hooks/list", "id": 2, "params": {}}],
            2,
        )
        hooks = hook_config["result"]["data"][0]["hooks"]
        self.assertTrue(
            any(hook["eventName"].lower() == "sessionstart" and hook["enabled"] for hook in hooks),
            "Codex should register the enabled plugin SessionStart hook",
        )

        # Run the exact installed hook entry point with Codex's SessionStart payload.
        hook_environment = environment.copy()
        hook_environment.update(
            {"PLUGIN_ROOT": str(installed_path), "PLUGIN_DATA": str(self.root / "plugin-data")}
        )
        hook_result = subprocess.run(
            [sys.executable, str(installed_path / "scripts" / "load_claude_skills.py"), "--hook"],
            input=json.dumps(
                {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.cwd)}
            ),
            check=True,
            capture_output=True,
            text=True,
            env=hook_environment,
        )
        self.assertIn("hookSpecificOutput", json.loads(hook_result.stdout))
        source_paths = {"skill1": skill1, "command1": command1}
        for name in ("skill1", "command1"):
            wrapper = codex_home / "skills" / "claude-imported" / name / "SKILL.md"
            self.assertTrue(wrapper.is_file(), f"SessionStart hook did not generate the {name} wrapper")
            wrapper_text = wrapper.read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", wrapper_text)
            self.assertIn(str(source_paths[name]), wrapper_text)
            if name == "command1":
                self.assertIn("$ARGUMENTS", wrapper_text)
        self.assertTrue(skill1.is_file())
        self.assertTrue(command1.is_file())

        # A fresh Codex process indexes the wrappers produced by the hook.
        menu_requests = initialize_messages() + [
            {
                "method": "skills/list",
                "id": 2,
                "params": {"cwds": [str(self.cwd)], "forceReload": True},
            }
        ]
        response = launch_app_server(menu_requests, 2)
        skills = {skill["name"]: skill for skill in response["result"]["data"][0]["skills"]}
        for name in ("skill1", "command1"):
            menu_name = name
            self.assertIn(
                menu_name,
                skills,
                f"the nested Claude {name} should be present in Codex's skill catalog used by its menus",
            )
            self.assertTrue(skills[menu_name]["enabled"])
            self.assertTrue(skills[menu_name]["path"].endswith(f"/claude-imported/{name}/SKILL.md"))
        self.assertIn("nested project skill", skills["skill1"]["description"])
        self.assertIn("nested project command", skills["command1"]["description"])
        self.assertIn("claude-skills-to-codex:reload", skills)


if __name__ == "__main__":
    unittest.main()
