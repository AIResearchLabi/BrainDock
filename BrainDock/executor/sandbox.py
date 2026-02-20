"""Sandbox utilities for safe command execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_sandboxed(
    command: str,
    cwd: str,
    timeout: int = 60,
) -> tuple[bool, str]:
    """Run a command in a sandboxed subprocess.

    Args:
        command: Shell command to run.
        cwd: Working directory.
        timeout: Max seconds to wait.

    Returns:
        Tuple of (success, output_text).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, f"Command failed: {e}"


def write_file_safe(
    file_path: str,
    content: str,
    project_dir: str,
) -> tuple[bool, str]:
    """Write a file, ensuring it stays within the project directory.

    Args:
        file_path: Relative path within the project.
        content: File content to write.
        project_dir: Root project directory.

    Returns:
        Tuple of (success, message).
    """
    full_path = Path(project_dir) / file_path
    resolved = full_path.resolve()
    project_resolved = Path(project_dir).resolve()

    # Safety: ensure the path is within the project directory
    if not str(resolved).startswith(str(project_resolved)):
        return False, f"Path escapes project directory: {file_path}"

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return True, f"Written: {file_path}"
    except Exception as e:
        return False, f"Failed to write {file_path}: {e}"
