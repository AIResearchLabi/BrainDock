"""Minimal HTTP server for the BrainDock dashboard.

Serves the dashboard HTML and pipeline_state.json from the output directory.
Uses only stdlib — no external dependencies.
"""

from __future__ import annotations

import argparse
import os
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves dashboard HTML and output directory files."""

    def __init__(self, *args, dashboard_dir: str, output_dir: str, **kwargs):
        self.dashboard_dir = dashboard_dir
        self.output_dir = output_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        # Strip leading slash
        rel = path.lstrip("/")

        # pipeline_state.json comes from the output directory
        if rel == "pipeline_state.json":
            return os.path.join(self.output_dir, "pipeline_state.json")

        # Everything else comes from the dashboard directory
        if not rel or rel == "index.html":
            return os.path.join(self.dashboard_dir, "index.html")

        # Try dashboard dir first, then output dir
        dashboard_path = os.path.join(self.dashboard_dir, rel)
        if os.path.exists(dashboard_path):
            return dashboard_path
        return os.path.join(self.output_dir, rel)

    def end_headers(self):
        # Allow CORS for local dev and disable caching for live updates
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        # Quieter logging — only show errors
        if args and isinstance(args[0], str) and args[0].startswith("GET"):
            return
        super().log_message(format, *args)


def run_server(output_dir: str = "output", port: int = 8080) -> None:
    """Start the dashboard HTTP server."""
    dashboard_dir = str(Path(__file__).parent)
    output_dir = os.path.abspath(output_dir)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    handler = partial(
        DashboardHandler,
        dashboard_dir=dashboard_dir,
        output_dir=output_dir,
    )

    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"BrainDock Dashboard running at http://localhost:{port}")
    print(f"  Serving output from: {output_dir}")
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
        help="Directory containing pipeline_state.json (default: output)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to serve on (default: 8080)",
    )
    return parser.parse_args(argv)
