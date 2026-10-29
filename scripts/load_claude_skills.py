#!/usr/bin/env python3
"""Discover Claude Code skills and commands and render Codex SessionStart context.

The bridge intentionally loads an index instead of copying skill instructions into
the plugin. Claude Code skills remain in their source directories, so changes are
picked up on the next session start or reload skill invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


DESCRIPTION_LIMIT = 240
READ_LIMIT = 256 * 1024


@dataclass(frozen=True)
class Skill:
    name: str
    path: str
    source: str
    kind: str
    description: str


def skill_roots(cwd: Path) -> list[tuple[Path, str]]:
    """Return project skill and command roots first, then global roots."""

    roots: list[tuple[Path, str]] = []
    global_base = Path.home() / ".claude"
    global_roots = [
        (global_base / "skills").resolve(),
        (global_base / "commands").resolve(),
    ]

    # Include the current project and any parent project roots. This lets Codex
    # work when it was started from a nested directory. The closest project
    # root wins when skill names collide.
    project_bases = [cwd, *cwd.parents]
    for base in project_bases:
        for kind in ("skills", "commands"):
            candidate = (base / ".claude" / kind).resolve()
            if candidate not in global_roots and candidate.is_dir():
                roots.append((candidate, "project"))

    for candidate in global_roots:
        if candidate.is_dir():
            roots.append((candidate, "global"))

    return roots


def _skill_name(path: Path, root: Path) -> str:
    relative_parent = path.parent.relative_to(root).as_posix()
    return root.parent.name if relative_parent == "." else relative_parent


def _declared_name(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    frontmatter = text.split("\n---", 1)[0]
    for line in frontmatter.splitlines()[1:]:
        if re.match(r"^name:\s*", line):
            value = line.split(":", 1)[1].strip().strip("'\"")
            return value or None
    return None


def _description(text: str, fallback: str) -> str:
    value = ""
    frontmatter = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
    frontmatter_lines = frontmatter.splitlines()[1:]
    for index, line in enumerate(frontmatter_lines):
        if not re.match(r"^description:\s*", line):
            continue
        raw_value = line.split(":", 1)[1].strip()
        if raw_value in {">", "|", ">-", "|-", ">+", "|+"}:
            continuation: list[str] = []
            for continuation_line in frontmatter_lines[index + 1 :]:
                if continuation_line and not continuation_line[0].isspace():
                    break
                continuation.append(continuation_line.strip())
            value = " ".join(continuation)
        else:
            value = raw_value.strip("'\"")
        break

    if not value:
        heading = re.search(r"^#{1,2}\s+(.+?)\s*$", text, re.MULTILINE)
        value = heading.group(1).strip() if heading else ""

    if not value:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("---"):
                value = line
                break

    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > DESCRIPTION_LIMIT:
        value = value[: DESCRIPTION_LIMIT - 1].rstrip() + "…"
    return value or fallback


def _skill_files(root: Path) -> list[Path]:
    """Find SKILL.md files, including skills linked into .claude/skills."""

    result: list[Path] = []
    visited_directories: set[str] = set()
    for directory, directory_names, file_names in os.walk(root, followlinks=True):
        real_directory = os.path.normcase(os.path.realpath(directory))
        if real_directory in visited_directories:
            directory_names[:] = []
            continue
        visited_directories.add(real_directory)
        if "SKILL.md" in file_names:
            result.append(Path(directory) / "SKILL.md")
    return sorted(result)


def _command_files(root: Path) -> list[Path]:
    """Find Claude command Markdown files, including nested command groups."""

    result: list[Path] = []
    visited_directories: set[str] = set()
    for directory, directory_names, file_names in os.walk(root, followlinks=True):
        real_directory = os.path.normcase(os.path.realpath(directory))
        if real_directory in visited_directories:
            directory_names[:] = []
            continue
        visited_directories.add(real_directory)
        result.extend(Path(directory) / filename for filename in file_names if filename.endswith(".md"))
    return sorted(result)


def discover(cwd: Path) -> tuple[list[Skill], list[tuple[Path, str]], list[str]]:
    roots = skill_roots(cwd)
    discovered: list[Skill] = []
    skipped_duplicates: list[str] = []
    seen_names: set[str] = set()

    for root, source in roots:
        kind = "skill" if root.name == "skills" else "command"
        try:
            files = _skill_files(root) if kind == "skill" else _command_files(root)
        except OSError:
            continue

        for path in files:
            try:
                if not path.is_file():
                    continue
                # Claude's trash directory contains intentionally retired skills;
                # they should not be offered as active Codex skills.
                if ".trash" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")[:READ_LIMIT]
                if kind == "command":
                    name = path.relative_to(root).with_suffix("").as_posix().replace("/", "-")
                else:
                    name = _declared_name(text) or _skill_name(path, root)
            except (OSError, ValueError):
                continue

            if name in seen_names:
                skipped_duplicates.append(name)
                continue

            seen_names.add(name)
            discovered.append(
                Skill(
                    name=name,
                    path=str(path),
                    source=source,
                    kind=kind,
                    description=_description(
                        text,
                        "Claude Code command instructions" if kind == "command" else "Claude Code skill instructions",
                    ),
                )
            )

    return discovered, roots, sorted(set(skipped_duplicates))


def _cache(discovered: list[Skill], roots: list[tuple[Path, str]], cwd: Path) -> None:
    plugin_data = os.environ.get("PLUGIN_DATA")
    if not plugin_data:
        return

    try:
        destination = Path(plugin_data) / "claude-skills.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "cwd": str(cwd),
            "roots": [{"path": str(path), "source": source} for path, source in roots],
            "skills": [asdict(skill) for skill in discovered],
        }
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        # The context output is the source of truth; cache persistence is best effort.
        pass


def _materialize_native_skills(discovered: list[Skill]) -> None:
    """Create small Codex-discoverable wrappers for the discovered Claude skills.

    Codex indexes plugin skills at session start, before SessionStart hooks run,
    so newly generated wrappers become visible after the next session starts.
    The plugin package is an install artifact; materialize into Codex's user
    skill directory and replace only this bridge's generated subtree.
    """
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    destination = codex_home / "skills" / "claude-imported"
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for child in destination.iterdir():
            if child.is_dir():
                for item in child.iterdir():
                    if item.is_file():
                        item.unlink()
                child.rmdir()
            elif child.is_file():
                child.unlink()
        for skill in discovered:
            slug = re.sub(r"[^a-z0-9-]+", "-", skill.name.lower()).strip("-") or "skill"
            name = slug
            description = f"Claude Code {skill.kind} ({skill.source}): {skill.description}"
            safe_description = description.replace("\n", " ").replace('"', "'")
            folder = destination / slug
            folder.mkdir(parents=True, exist_ok=True)
            body = (
                f"---\nname: {name}\ndescription: \"{safe_description}\"\n---\n\n"
                "Use this imported Claude Code instruction when relevant. Read and follow its complete "
                f"contents at `{skill.path}`. Its supporting files remain alongside that file.\n"
            )
            if skill.kind == "command":
                body += (
                    "Treat the source as a prompt template. Replace `$ARGUMENTS` and positional "
                    "placeholders such as `$1` with arguments supplied after this skill is invoked.\n"
                )
            (folder / "SKILL.md").write_text(body, encoding="utf-8")
    except OSError:
        # Listing generation is best-effort; the injected index still works.
        pass


def render_context(cwd: Path) -> tuple[str, dict[str, object]]:
    discovered, roots, duplicates = discover(cwd)
    _cache(discovered, roots, cwd)
    _materialize_native_skills(discovered)

    lines = [
        "Claude Code skill bridge refreshed.",
        f"Working directory: {cwd}",
        f"Discovered {len(discovered)} Claude Code skill(s) and command(s) from ~/.claude and project .claude locations.",
        "Project-local items take precedence over global items with the same name.",
        "",
        "Use a discovered skill or command only when it is relevant. Before applying one, read its complete source file from the path below; the index is intentionally metadata-only.",
    ]

    if discovered:
        lines.extend(["", "Available skills and commands:"])
        for skill in discovered:
            lines.append(f"- {skill.name} [{skill.source} {skill.kind}] — {skill.description}")
            lines.append(f"  Source: {skill.path}")
    else:
        lines.extend(["", "No Claude Code skill or command files were found."])

    if roots:
        lines.extend(["", "Scanned roots:"])
        lines.extend(f"- {source}: {path}" for path, source in roots)

    if duplicates:
        lines.extend(["", f"Skipped {len(duplicates)} lower-precedence duplicate skill name(s): {', '.join(duplicates)}."])

    lines.extend([
        "",
        "Use the reload skill to rescan during this turn; new menu entries appear after a new Codex session indexes the generated skills.",
    ])

    payload = {
        "count": len(discovered),
        "cwd": str(cwd),
        "roots": [{"path": str(path), "source": source} for path, source in roots],
        "skills": [asdict(skill) for skill in discovered],
        "duplicates": duplicates,
    }
    return "\n".join(lines), payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", action="store_true", help="Read Codex hook input and emit SessionStart JSON.")
    parser.add_argument("--cwd", type=Path, help="Working directory to scan when not using --hook.")
    parser.add_argument("--json", action="store_true", help="Emit the discovered skill metadata as JSON.")
    args = parser.parse_args()

    hook_input: dict[str, object] = {}
    if args.hook:
        try:
            hook_input = json.load(sys.stdin)
        except (json.JSONDecodeError, OSError):
            hook_input = {}

    raw_cwd = args.cwd or hook_input.get("cwd") or os.getcwd()
    cwd = Path(str(raw_cwd)).expanduser().resolve()

    context, payload = render_context(cwd)
    if args.hook:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )
    elif args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(context + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
