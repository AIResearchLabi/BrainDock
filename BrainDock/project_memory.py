"""Project Memory — scans project directory to build context for agents."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "egg-info",
    ".eggs", ".cache", ".next", ".nuxt",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".exe", ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}

PRIORITY_FILES = [
    "main.py", "app.py", "manage.py", "index.py", "server.py",
    "index.js", "index.ts", "app.js", "app.ts", "server.js", "server.ts",
    "package.json", "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "README.md", "README.rst",
    "run.sh", "start.sh",
]

MAX_SNAPSHOT_BYTES = 50_000
MAX_FILE_BYTES = 8_000


@dataclass
class ProjectSnapshot:
    """Snapshot of a project directory for agent context."""
    file_tree: str = ""
    key_file_contents: dict[str, str] = field(default_factory=dict)
    total_files: int = 0
    total_size: int = 0

    def to_context_string(self) -> str:
        """Format snapshot as a context string for LLM prompts."""
        parts = []
        if self.file_tree:
            parts.append(f"File tree ({self.total_files} files):\n{self.file_tree}")
        if self.key_file_contents:
            parts.append("Key file contents:")
            for path, content in self.key_file_contents.items():
                parts.append(f"\n--- {path} ---\n{content}")
        if not parts:
            return "(empty project directory)"
        return "\n".join(parts)


def _should_skip_dir(name: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    return name in SKIP_DIRS or name.startswith(".")


def _is_binary(path: str) -> bool:
    """Check if a file is likely binary based on extension."""
    return Path(path).suffix.lower() in BINARY_EXTENSIONS


def _build_tree(project_dir: str) -> tuple[str, list[tuple[str, float, int]]]:
    """Build a text tree and collect file metadata.

    Returns:
        Tuple of (tree_string, list of (relative_path, mtime, size)).
    """
    lines = []
    files_meta = []
    project_path = Path(project_dir).resolve()

    for root, dirs, files in os.walk(project_dir):
        # Filter out skip dirs in-place
        dirs[:] = sorted(d for d in dirs if not _should_skip_dir(d))
        files = sorted(files)

        rel_root = os.path.relpath(root, project_dir)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        indent = "  " * depth

        if rel_root != ".":
            lines.append(f"{indent}{os.path.basename(root)}/")

        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, project_dir)
            lines.append(f"{indent}  {f}")

            try:
                stat = os.stat(full_path)
                files_meta.append((rel_path, stat.st_mtime, stat.st_size))
            except OSError:
                files_meta.append((rel_path, 0.0, 0))

    return "\n".join(lines), files_meta


def scan_project(project_dir: str) -> ProjectSnapshot:
    """Scan a project directory and return a snapshot for agent context.

    Reads priority files first, then most recently modified files,
    staying within the byte budget.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ProjectSnapshot with file tree and key file contents.
    """
    if not os.path.isdir(project_dir):
        return ProjectSnapshot()

    tree_str, files_meta = _build_tree(project_dir)
    total_files = len(files_meta)
    total_size = sum(size for _, _, size in files_meta)

    # Build reading order: priority files first, then by most recent mtime
    priority_set = set(PRIORITY_FILES)
    priority_list = []
    other_list = []

    for rel_path, mtime, size in files_meta:
        basename = os.path.basename(rel_path)
        if basename in priority_set:
            priority_list.append((rel_path, mtime, size))
        else:
            other_list.append((rel_path, mtime, size))

    # Sort priority files by their position in PRIORITY_FILES
    priority_order = {name: i for i, name in enumerate(PRIORITY_FILES)}
    priority_list.sort(key=lambda x: priority_order.get(os.path.basename(x[0]), 999))

    # Sort other files by most recently modified
    other_list.sort(key=lambda x: x[1], reverse=True)

    read_order = priority_list + other_list

    # Read files within budget
    key_contents: dict[str, str] = {}
    budget_used = len(tree_str.encode("utf-8", errors="replace"))

    for rel_path, _, size in read_order:
        if budget_used >= MAX_SNAPSHOT_BYTES:
            break
        if _is_binary(rel_path):
            continue
        if size > MAX_FILE_BYTES:
            continue
        if size == 0:
            continue

        full_path = os.path.join(project_dir, rel_path)
        try:
            content = Path(full_path).read_text(errors="replace")
            content_bytes = len(content.encode("utf-8", errors="replace"))
            if content_bytes > MAX_FILE_BYTES:
                content = content[:MAX_FILE_BYTES] + "\n... (truncated)"
                content_bytes = MAX_FILE_BYTES
            if budget_used + content_bytes > MAX_SNAPSHOT_BYTES:
                break
            key_contents[rel_path] = content
            budget_used += content_bytes
        except OSError:
            continue

    return ProjectSnapshot(
        file_tree=tree_str,
        key_file_contents=key_contents,
        total_files=total_files,
        total_size=total_size,
    )
