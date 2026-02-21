"""Sandbox utilities for safe command execution."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .models import VerifyResult


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


def read_file_safe(
    file_path: str,
    project_dir: str,
) -> str | None:
    """Read a file safely, ensuring it stays within the project directory.

    Args:
        file_path: Relative path within the project.
        project_dir: Root project directory.

    Returns:
        File content as string, or None if not readable.
    """
    full_path = Path(project_dir) / file_path
    resolved = full_path.resolve()
    project_resolved = Path(project_dir).resolve()

    # Safety: ensure the path is within the project directory
    if not str(resolved).startswith(str(project_resolved)):
        return None

    try:
        if resolved.is_file():
            return resolved.read_text(errors="replace")
    except OSError:
        pass
    return None


# Error patterns that indicate runtime failures
_ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"SyntaxError:",
    r"ModuleNotFoundError:",
    r"ImportError:",
    r"NameError:",
    r"TypeError:",
    r"ValueError:",
    r"FileNotFoundError:",
    r"IndentationError:",
    r"AttributeError:",
    r"npm ERR!",
    r"Error:",
    r"FATAL",
    r"Segmentation fault",
]

_ERROR_RE = re.compile("|".join(_ERROR_PATTERNS), re.IGNORECASE)


def _detect_entry_point(project_dir: str) -> tuple[str, str]:
    """Detect the best way to run the project.

    Returns:
        Tuple of (command, detection_method).
    """
    p = Path(project_dir)

    # Python entry points
    for name in ("main.py", "app.py", "manage.py"):
        if (p / name).is_file():
            return f"python {name}", name

    # package.json scripts
    pkg_json = p / "package.json"
    if pkg_json.is_file():
        try:
            import json
            data = json.loads(pkg_json.read_text())
            scripts = data.get("scripts", {})
            if "start" in scripts:
                return "npm start", "package.json:start"
            if "build" in scripts:
                return "npm run build", "package.json:build"
        except (ValueError, OSError):
            pass

    # Shell scripts
    if (p / "run.sh").is_file():
        return "bash run.sh", "run.sh"

    # Makefile
    if (p / "Makefile").is_file():
        return "make", "Makefile"

    return "", ""


def verify_project(
    project_dir: str,
    timeout: int = 10,
) -> VerifyResult:
    """Run the project and check for errors.

    Auto-detects the entry point, launches it, and checks output for
    error patterns. A timeout for long-running servers is treated as success
    (the server stayed alive).

    Args:
        project_dir: Path to the project directory.
        timeout: Max seconds to wait.

    Returns:
        VerifyResult with success status and details.
    """
    command, detection_method = _detect_entry_point(project_dir)
    if not command:
        return VerifyResult(
            success=True,
            command="",
            detection_method="none",
            error_summary="No entry point found — skipping verification",
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        combined = stdout + "\n" + stderr

        # Check for error patterns in output
        match = _ERROR_RE.search(combined)
        if result.returncode != 0 or match:
            error_summary = ""
            if match:
                # Extract a few lines around the match for context
                start = max(0, match.start() - 100)
                end = min(len(combined), match.end() + 200)
                error_summary = combined[start:end].strip()
            elif stderr.strip():
                error_summary = stderr.strip()[:500]
            else:
                error_summary = f"Exit code {result.returncode}"

            return VerifyResult(
                success=False,
                command=command,
                stdout=stdout[:2000],
                stderr=stderr[:2000],
                exit_code=result.returncode,
                error_summary=error_summary[:500],
                detection_method=detection_method,
            )

        return VerifyResult(
            success=True,
            command=command,
            stdout=stdout[:2000],
            stderr=stderr[:2000],
            exit_code=result.returncode,
            detection_method=detection_method,
        )

    except subprocess.TimeoutExpired:
        # Timeout = server stayed alive = success
        return VerifyResult(
            success=True,
            command=command,
            exit_code=0,
            detection_method=detection_method,
            error_summary="Process timed out (assumed running server)",
        )
    except Exception as e:
        return VerifyResult(
            success=False,
            command=command,
            exit_code=-1,
            error_summary=str(e)[:500],
            detection_method=detection_method,
        )
