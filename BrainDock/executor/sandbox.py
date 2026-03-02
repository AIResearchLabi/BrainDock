"""Sandbox utilities for safe command execution."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .models import VerifyResult


def _sanitize_command_for_posix(command: str) -> str:
    """Rewrite common bash-isms to POSIX-compatible equivalents.

    Many LLM-generated commands use bash syntax that fails under /bin/sh
    (which Python subprocess uses internally in generated scripts).
    This rewrites the most common offenders.
    """
    cmd = command.strip()

    # Remove outer grouping parentheses: ( cmd1 && cmd2 ) -> cmd1 && cmd2
    if cmd.startswith("(") and cmd.endswith(")"):
        inner = cmd[1:-1].strip()
        # Only unwrap if it looks like a simple command group, not a subshell
        if ";" in inner or "&&" in inner or "||" in inner:
            cmd = inner

    # Replace [[ ]] with [ ] for test expressions
    cmd = re.sub(r'\[\[(.+?)\]\]', r'[ \1 ]', cmd)

    return cmd


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
    command = _sanitize_command_for_posix(command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
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


def _looks_like_shell_command(content: str) -> bool:
    """Detect if content looks like a shell command.

    Used to prevent false positives from _looks_like_description when
    validating run_command actions — shell commands often look like prose.
    """
    if not content or not content.strip():
        return False

    stripped = content.strip()

    # Shell operators are a strong signal
    _SHELL_OPS = ("&&", "||", "|", ">>", "<<", "2>&1")
    if any(op in stripped for op in _SHELL_OPS):
        return True

    # First token is a known command/binary
    first_token = stripped.split()[0] if stripped.split() else ""
    # Strip leading path (e.g. /usr/bin/python -> python)
    base_cmd = first_token.rsplit("/", 1)[-1]

    _KNOWN_COMMANDS = {
        "cd", "python", "python3", "node", "npm", "npx", "pip", "pip3",
        "make", "bash", "sh", "zsh", "cargo", "go", "java", "javac",
        "gcc", "g++", "ruby", "perl", "dotnet", "docker", "git",
        "curl", "wget", "ls", "cat", "echo", "mkdir", "rm", "cp", "mv",
        "chmod", "chown", "grep", "find", "sed", "awk", "tar", "zip",
        "unzip", "test", "pytest", "unittest", "tox", "flask", "django-admin",
        "uvicorn", "gunicorn", "celery", "redis-server", "nginx",
    }
    if base_cmd in _KNOWN_COMMANDS:
        return True

    # Contains flags like -m, --flag
    if " -" in stripped:
        return True

    return False


def _looks_like_description(content: str) -> bool:
    """Detect if content is a natural-language description rather than code.

    Returns True if the content appears to be a prose description that was
    mistakenly provided instead of actual source code.
    """
    if not content or len(content) < 20:
        return False

    # Check first non-empty line
    first_line = ""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break

    if not first_line:
        return False

    # Known description patterns from LLM failures
    _DESC_STARTS = (
        "Wrote ", "Updated ", "Added ", "Created ", "Implemented ",
        "Refactored ", "Modified ", "Changed ", "Wrapped ", "Rewrote ",
        "Already exists", "No changes needed", "The file ",
        "All tests ", "Tests pass", "Ran ", "OK (", "PASSED",
        "Successfully ", "Verified ", "Confirmed ",
    )
    if first_line.startswith(_DESC_STARTS):
        return True

    # If the entire content is a single line of prose (no newlines, no code
    # punctuation), it's almost certainly a description
    if "\n" not in content.strip():
        code_chars = sum(1 for c in content if c in "{}()[];=<>:#+@!&|^~\\")
        if code_chars < 3 and len(content) > 40:
            return True

    return False


def _validate_source_content(
    file_path: str,
    content: str,
    project_dir: str = "",
) -> tuple[bool, str]:
    """Validate that source file content looks like actual code, not a description.

    Also performs pre-flight import validation for Python files to catch
    imports of non-existent modules before writing to disk.

    Returns (ok, error_message).
    """
    ext = Path(file_path).suffix.lower()
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
                       ".rs", ".rb", ".php", ".c", ".cpp", ".h", ".css",
                       ".html", ".sh", ".sql"}

    if ext not in code_extensions:
        return True, ""

    if _looks_like_description(content):
        return False, (
            f"Content for {file_path} appears to be a natural-language "
            f"description, not source code. First 100 chars: "
            f"{content[:100]!r}"
        )

    # For Python files, try to compile to catch obvious syntax issues
    if ext == ".py" and content.strip():
        try:
            compile(content, file_path, "exec")
        except SyntaxError as e:
            return False, (
                f"Python syntax error in {file_path}: {e.msg} "
                f"(line {e.lineno})"
            )

        # Pre-flight import validation: catch imports of forbidden or
        # non-existent modules before execution wastes LLM retries
        import_issues = _validate_python_imports(content, file_path, project_dir)
        if import_issues:
            return False, import_issues

    return True, ""


# Modules that should never be imported from generated project code.
# These are BrainDock internals that don't exist in the output directory.
_FORBIDDEN_IMPORT_PREFIXES = (
    "BrainDock",
    "braindock",
)


def _validate_python_imports(
    content: str,
    file_path: str,
    project_dir: str = "",
) -> str:
    """Check Python source for imports of forbidden or unavailable modules.

    Returns an error string if issues found, empty string if OK.
    """
    import ast

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return ""  # Already caught by compile() above

    bad_imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if any(mod == prefix or mod.startswith(prefix + ".")
                       for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                    bad_imports.append(
                        f"line {node.lineno}: import {mod}"
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(mod == prefix or mod.startswith(prefix + ".")
                   for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                bad_imports.append(
                    f"line {node.lineno}: from {mod} import ..."
                )
            # Also check if relative imports reference modules that
            # don't exist in the project (only for non-relative imports)
            if node.level == 0 and project_dir and mod:
                top_module = mod.split(".")[0]
                if not _module_exists_in_project(top_module, project_dir, file_path):
                    # Only flag if it's not a stdlib or well-known module
                    if not _is_likely_available(top_module):
                        bad_imports.append(
                            f"line {node.lineno}: from {mod} import ... "
                            f"(module '{top_module}' not found in project)"
                        )

    if not bad_imports:
        return ""

    return (
        f"Import validation failed in {file_path}:\n"
        + "\n".join(f"  - {issue}" for issue in bad_imports)
        + "\n\nThe generated project is isolated and cannot import "
        "BrainDock internals. Only import from Python stdlib, project-local "
        "modules, or packages in requirements.txt."
    )


def _module_exists_in_project(module_name: str, project_dir: str, source_file: str) -> bool:
    """Check if a module exists as a directory or .py file in the project."""
    p = Path(project_dir)
    # Check as package directory
    if (p / module_name).is_dir() and (p / module_name / "__init__.py").exists():
        return True
    # Check as .py file
    if (p / f"{module_name}.py").is_file():
        return True
    # Check relative to source file's parent
    source_parent = Path(source_file).parent
    if source_parent != Path("."):
        full_parent = p / source_parent
        if (full_parent / module_name).is_dir():
            return True
        if (full_parent / f"{module_name}.py").is_file():
            return True
    return False


# Stdlib + common third-party modules that are likely available.
# This is not exhaustive — it covers the most common false positives.
_STDLIB_AND_COMMON = {
    "abc", "argparse", "ast", "asyncio", "base64", "bisect", "builtins",
    "calendar", "cgi", "cmd", "codecs", "collections", "colorsys",
    "concurrent", "configparser", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "dis", "email",
    "enum", "errno", "fcntl", "fileinput", "fnmatch", "fractions",
    "ftplib", "functools", "getpass", "gettext", "glob", "gzip",
    "hashlib", "heapq", "hmac", "html", "http", "imaplib", "importlib",
    "inspect", "io", "ipaddress", "itertools", "json", "keyword",
    "linecache", "locale", "logging", "lzma", "mailbox", "math",
    "mimetypes", "multiprocessing", "numbers", "operator", "os",
    "pathlib", "pickle", "pkgutil", "platform", "plistlib", "pprint",
    "profile", "pstats", "queue", "random", "re", "readline",
    "reprlib", "resource", "secrets", "select", "shelve", "shlex",
    "shutil", "signal", "site", "smtplib", "socket", "socketserver",
    "sqlite3", "ssl", "stat", "statistics", "string", "struct",
    "subprocess", "sys", "syslog", "tarfile", "tempfile", "termios",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "traceback", "tracemalloc", "tty", "turtle",
    "types", "typing", "unicodedata", "unittest", "urllib", "uuid",
    "venv", "warnings", "wave", "weakref", "webbrowser", "xml",
    "xmlrpc", "zipfile", "zipimport", "zlib",
    # Common third-party
    "pip", "setuptools", "pkg_resources", "wheel",
    "requests", "flask", "django", "fastapi", "uvicorn", "gunicorn",
    "numpy", "pandas", "scipy", "matplotlib", "seaborn", "sklearn",
    "torch", "tensorflow", "keras", "transformers",
    "pytest", "tox", "black", "ruff", "mypy", "pylint",
    "pydantic", "sqlalchemy", "alembic", "celery", "redis",
    "boto3", "botocore", "docker", "yaml", "pyyaml", "toml",
    "click", "typer", "rich", "httpx", "aiohttp", "websockets",
    "jinja2", "markdown", "beautifulsoup4", "bs4", "lxml",
    "pillow", "PIL", "cv2", "playwright",
}


def _is_likely_available(module_name: str) -> bool:
    """Check if a module is stdlib or a well-known third-party package."""
    return module_name in _STDLIB_AND_COMMON


def write_file_safe(
    file_path: str,
    content: str,
    project_dir: str,
) -> tuple[bool, str]:
    """Write a file, ensuring it stays within the project directory.

    Validates that source files contain actual code (not descriptions)
    and that Python files have valid syntax before writing.

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

    # Validate source file content before writing
    valid, err = _validate_source_content(file_path, content, project_dir)
    if not valid:
        return False, err

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


def scan_for_corrupted_files(project_dir: str) -> list[dict]:
    """Scan project directory for source files containing descriptions instead of code.

    Used on resume to detect files corrupted by prior LLM failures.

    Returns:
        List of dicts with 'path' (relative), 'reason', and 'absolute_path'.
    """
    corrupted = []
    project_path = Path(project_dir)
    if not project_path.is_dir():
        return corrupted

    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
                       ".rs", ".rb", ".php", ".c", ".cpp", ".h"}

    for file_path in project_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in code_extensions:
            continue
        # Skip __pycache__
        if "__pycache__" in file_path.parts:
            continue

        try:
            content = file_path.read_text(errors="replace")
        except OSError:
            continue

        # Skip empty files (likely __init__.py placeholders)
        if not content.strip():
            continue

        if _looks_like_description(content):
            rel_path = str(file_path.relative_to(project_path))
            corrupted.append({
                "path": rel_path,
                "reason": f"File contains description instead of code: {content[:80]!r}",
                "absolute_path": str(file_path),
            })

    return corrupted


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
            executable="/bin/bash",
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
        # For server-like commands (npm start, gunicorn, flask, uvicorn),
        # timeout means the server stayed alive = success.
        # For test/script commands (python main.py, make), timeout is a failure.
        _SERVER_INDICATORS = ("npm start", "flask run", "uvicorn", "gunicorn",
                              "celery", "redis-server", "nginx", "serve")
        is_server = any(ind in command for ind in _SERVER_INDICATORS)
        if is_server:
            return VerifyResult(
                success=True,
                command=command,
                exit_code=0,
                detection_method=detection_method,
                error_summary="Process timed out (assumed running server)",
            )
        return VerifyResult(
            success=False,
            command=command,
            exit_code=-1,
            detection_method=detection_method,
            error_summary=f"Command timed out after {timeout}s (not a server command)",
        )
    except Exception as e:
        return VerifyResult(
            success=False,
            command=command,
            exit_code=-1,
            error_summary=str(e)[:500],
            detection_method=detection_method,
        )
