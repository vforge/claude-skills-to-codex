#!/usr/bin/env python3
"""Discover Claude Code skills and render a Codex SessionStart context block.

The bridge intentionally loads an index instead of copying skill instructions into
the plugin. Claude Code skills remain in their source directories, so changes are
picked up on the next session start or /reload-skills invocation.
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
from typing import Iterable


DESCRIPTION_LIMIT = 240
READ_LIMIT = 256 * 1024


@dataclass(frozen=True)
class Skill:
    name: str
    path: str
    source: str
    description: str


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def skill_roots(cwd: Path) -> list[tuple[Path, str]]:
    """Return project roots first, then the global Claude Code skills root."""

    roots: list[tuple[Path, str]] = []
    global_root = (Path.home() / ".claude" / "skills").resolve()

    # Include the current project and any parent project roots. This lets Codex
    # work when it was started from a nested directory. The closest project
    # root wins when skill names collide.
    project_candidates = [cwd / ".claude" / "skills", *(
        parent / ".claude" / "skills" for parent in cwd.parents
    )]
    for candidate in _unique_paths(project_candidates):
        if candidate != global_root and candidate.is_dir():
            roots.append((candidate, "project"))

    if global_root.is_dir():
        roots.append((global_root, "global"))

    return roots


def _skill_name(path: Path, root: Path) -> str:
    relative_parent = path.parent.relative_to(root).as_posix()
    return root.parent.name if relative_parent == "." else relative_parent


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


def discover(cwd: Path) -> tuple[list[Skill], list[tuple[Path, str]], list[str]]:
    roots = skill_roots(cwd)
    discovered: list[Skill] = []
    skipped_duplicates: list[str] = []
    seen_names: set[str] = set()

    for root, source in roots:
        try:
            files = _skill_files(root)
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
                name = _skill_name(path, root)
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
                    description=_description(text, "Claude Code skill instructions"),
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
    Keep these separate from the bridge's own skill and replace only our
    generated subtree.
    """
    plugin_root = os.environ.get("PLUGIN_ROOT")
    if not plugin_root:
        return
    destination = Path(plugin_root) / "skills" / "claude-imported"
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
            name = f"claude-{slug}"
            description = f"Claude Code skill ({skill.source}): {skill.description}"
            safe_description = description.replace("\n", " ").replace('"', "'")
            folder = destination / slug
            folder.mkdir(parents=True, exist_ok=True)
            body = (
                f"---\nname: {name}\ndescription: \"{safe_description}\"\n---\n\n"
                "Use this Claude Code skill when relevant. Read and follow its complete "
                f"instructions at `{skill.path}`. Its supporting files remain alongside that file.\n"
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
        f"Discovered {len(discovered)} Claude Code skill(s) from ~/.claude/skills and project .claude/skills locations.",
        "Project-local skills take precedence over global skills with the same name.",
        "",
        "Use a discovered skill only when it is relevant. Before applying one, read its complete SKILL.md from the path below; the index is intentionally metadata-only.",
    ]

    if discovered:
        lines.extend(["", "Available skills:"])
        for skill in discovered:
            lines.append(f"- {skill.name} [{skill.source}] — {skill.description}")
            lines.append(f"  SKILL.md: {skill.path}")
    else:
        lines.extend(["", "No Claude Code SKILL.md files were found."])

    if roots:
        lines.extend(["", "Scanned roots:"])
        lines.extend(f"- {source}: {path}" for path, source in roots)

    if duplicates:
        lines.extend(["", f"Skipped {len(duplicates)} lower-precedence duplicate skill name(s): {', '.join(duplicates)}."])

    lines.extend([
        "",
        "The /reload-skills command repeats this scan during the current conversation.",
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
