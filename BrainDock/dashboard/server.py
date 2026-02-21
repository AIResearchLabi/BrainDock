"""HTTP server for the BrainDock dashboard.

Serves the 3-tab SPA and API endpoints for pipeline interaction.
Uses only stdlib — no external dependencies.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .runner import PipelineRunner

logger = logging.getLogger("braindock.server")


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves dashboard HTML and handles API requests."""

    def __init__(self, *args, dashboard_dir: str, output_dir: str, runner: PipelineRunner, **kwargs):
        self.dashboard_dir = dashboard_dir
        self.output_dir = output_dir
        self.runner = runner
        self._headers_sent = False
        super().__init__(*args, **kwargs)

    # ── Routing ───────────────────────────────────────────────────

    @staticmethod
    def _extract_api_path(full_path: str) -> str | None:
        """Extract '/api/...' from a path that may have a proxy prefix.

        Handles both '/api/state' and '/proxy/3000/api/state'.
        Returns the '/api/...' portion, or None if not an API path.
        """
        idx = full_path.find("/api/")
        if idx == -1:
            # Also handle '/api' without trailing content
            if full_path.rstrip("/").endswith("/api"):
                return "/api"
            return None
        return full_path[idx:].rstrip("/")

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        api_path = self._extract_api_path(parsed.path)

        # API routes — always return JSON
        if api_path is not None:
            try:
                if api_path == "/api/state":
                    self._api_state()
                elif api_path == "/api/runs":
                    self._api_runs()
                elif api_path == "/api/activities":
                    since = int(params.get("since", ["0"])[0])
                    self._api_activities(since)
                elif api_path == "/api/chat":
                    since = int(params.get("since", ["0"])[0])
                    self._api_chat(since)
                elif api_path == "/api/logs":
                    since = int(params.get("since", ["0"])[0])
                    self._api_logs(since)
                else:
                    self._json_response({"error": "Not found"}, status=404)
            except Exception as e:
                self._safe_json_error(e)
            return

        # Static file serving
        try:
            super().do_GET()
        except Exception:
            pass

    def do_POST(self):
        parsed = urlparse(self.path)
        api_path = self._extract_api_path(parsed.path)

        try:
            body = self._read_body()

            if api_path == "/api/start":
                self._api_start(body)
            elif api_path == "/api/answers":
                self._api_answers(body)
            elif api_path == "/api/chat":
                self._api_send_chat(body)
            elif api_path == "/api/resume":
                self._api_resume(body)
            else:
                self._json_response({"error": "Not found"}, status=404)
        except Exception as e:
            self._safe_json_error(e)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self._api_handled = True
        self.end_headers()

    # ── Override send_error to return JSON for API routes ─────────

    def send_error(self, code, message=None, explain=None):
        """Override to return JSON for API routes instead of HTML."""
        path = getattr(self, 'path', '')
        parsed = urlparse(path)
        if self._extract_api_path(parsed.path) is not None:
            try:
                self._json_response(
                    {"error": message or f"HTTP {code}"},
                    status=code,
                )
            except Exception:
                pass
            return
        super().send_error(code, message, explain)

    # ── API Handlers ──────────────────────────────────────────────

    def _api_state(self):
        state = self.runner.get_state()
        if not state or (not state.get("_running") and not state.get("title")):
            # Fall back to disk-based state
            state = self._load_disk_state()
            state["_running"] = False
            state["_error"] = ""
            state["_pending_questions"] = None
            state["_pending_decisions"] = None
            state["_pending_understanding"] = ""
        self._json_response(state)

    def _api_runs(self):
        runs = self.runner.list_runs()
        self._json_response({"runs": runs})

    def _api_activities(self, since: int):
        data = self.runner.get_activities(since)
        self._json_response(data)

    def _api_chat(self, since: int):
        data = self.runner.get_chat(since)
        self._json_response(data)

    def _api_logs(self, since: int):
        data = self.runner.get_logs(since)
        self._json_response(data)

    def _api_start(self, body: dict):
        title = body.get("title", "").strip()
        problem = body.get("problem", "").strip()
        if not problem:
            self._json_response({"error": "problem is required"}, status=400)
            return
        if not title:
            title = problem[:60]
        logger.info("API /start: title=%r problem=%r", title, problem[:80])
        ok = self.runner.start(title, problem)
        if ok:
            self._json_response({"ok": True, "title": title})
        else:
            logger.warning("API /start: pipeline already running")
            self._json_response({"error": "Pipeline already running"}, status=409)

    def _api_answers(self, body: dict):
        answers = body.get("answers", {})
        ok = self.runner.submit_answers(answers)
        if ok:
            self._json_response({"ok": True})
        else:
            self._json_response({"error": "No pending questions"}, status=400)

    def _api_send_chat(self, body: dict):
        message = body.get("message", "").strip()
        if not message:
            self._json_response({"error": "message is required"}, status=400)
            return
        self.runner.send_chat(message)
        self._json_response({"ok": True})

    def _api_resume(self, body: dict):
        title = body.get("title", "").strip()
        if not title:
            self._json_response({"error": "title is required"}, status=400)
            return
        logger.info("API /resume: title=%r", title)
        ok = self.runner.resume(title)
        if ok:
            self._json_response({"ok": True, "title": title})
        else:
            logger.warning("API /resume: could not resume %r", title)
            self._json_response({"error": f"Could not resume '{title}'"}, status=404)

    # ── Helpers ───────────────────────────────────────────────────

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _json_response(self, data: dict, status: int = 200):
        if self._headers_sent:
            return
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self._api_handled = True
        self.end_headers()
        self._headers_sent = True
        self.wfile.write(body)

    def _safe_json_error(self, exc: Exception):
        """Send a JSON error response, handling double-send gracefully."""
        tb = traceback.format_exception_only(type(exc), exc)
        msg = "".join(tb).strip()
        sys.stderr.write(f"[Dashboard API error] {msg}\n")
        try:
            self._json_response({"error": msg}, status=500)
        except Exception:
            pass

    def _load_disk_state(self) -> dict:
        """Load latest pipeline_state.json from disk (for viewing past runs)."""
        # Scan output directory for the most recently modified state file
        best = {}
        if os.path.isdir(self.output_dir):
            for entry in os.listdir(self.output_dir):
                sp = os.path.join(self.output_dir, entry, "pipeline_state.json")
                if os.path.isfile(sp):
                    try:
                        with open(sp) as f:
                            data = json.load(f)
                        if data.get("spec") and data["spec"].get("title"):
                            best = data
                    except (json.JSONDecodeError, KeyError):
                        pass
        return best

    # ── Static file serving ───────────────────────────────────────

    def translate_path(self, path: str) -> str:
        rel = path.lstrip("/").split("?")[0]

        if not rel or rel == "index.html":
            return os.path.join(self.dashboard_dir, "index.html")

        dashboard_path = os.path.join(self.dashboard_dir, rel)
        if os.path.exists(dashboard_path):
            return dashboard_path
        return os.path.join(self.output_dir, rel)

    def end_headers(self):
        # Only add CORS for static file responses; API responses set their own
        if not getattr(self, '_api_handled', False):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
        self._api_handled = False
        super().end_headers()

    def log_message(self, format, *args):
        if args and isinstance(args[0], str) and (args[0].startswith("GET") or args[0].startswith("POST")):
            return
        super().log_message(format, *args)


def _setup_logging(verbose: bool = True) -> None:
    """Configure logging for BrainDock dashboard.

    Args:
        verbose: If True (default), log at INFO level. If False, only WARNINGS+.
    """
    level = logging.INFO if verbose else logging.WARNING
    fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stderr)
    # Quiet down noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def run_server(
    output_dir: str = "output",
    port: int = 3000,
    runner: PipelineRunner | None = None,
    verbose: bool = True,
) -> None:
    """Start the dashboard HTTP server."""
    _setup_logging(verbose)

    dashboard_dir = str(Path(__file__).parent)
    output_dir = os.path.abspath(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if runner is None:
        runner = PipelineRunner(output_dir=output_dir)

    handler = partial(
        DashboardHandler,
        dashboard_dir=dashboard_dir,
        output_dir=output_dir,
        runner=runner,
    )

    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    logger.info("BrainDock Dashboard running at http://localhost:%d", port)
    logger.info("Serving output from: %s", output_dir)
    logger.info("Logging: %s", "verbose" if verbose else "quiet")
    print(f"BrainDock Dashboard running at http://localhost:{port}")
    print(f"  Serving output from: {output_dir}")
    print(f"  Logging: {'verbose (use --no-log to disable)' if verbose else 'quiet'}")
    print(f"  Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        server.shutdown()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="braindock-dashboard",
        description="BrainDock Pipeline Dashboard — live visualization server",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory (default: output)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port to serve on (default: 3000)",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        default=False,
        help="Disable verbose terminal logging (enabled by default)",
    )
    return parser.parse_args(argv)
