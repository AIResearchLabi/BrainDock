"""Session persistence utilities for BrainDock agents.

Provides save/load/clear JSON session helpers as a mixin.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionMixin:
    """Mixin for agents that need session persistence."""

    session_file: str

    def _save_session_data(self, data: dict[str, Any]) -> None:
        """Save session data to the session file."""
        Path(self.session_file).write_text(json.dumps(data, indent=2))

    def _load_session_data(self) -> dict[str, Any] | None:
        """Load session data from the session file. Returns None if no file."""
        p = Path(self.session_file)
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def _clear_session(self) -> None:
        """Remove session file after successful completion."""
        p = Path(self.session_file)
        if p.exists():
            p.unlink()
