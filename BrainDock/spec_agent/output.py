"""Output formatters for the Spec Agent."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ProjectSpec


def to_json(spec: ProjectSpec, indent: int = 2) -> str:
    """Convert a ProjectSpec to formatted JSON string."""
    return json.dumps(spec.to_dict(), indent=indent)


def save_spec(spec: ProjectSpec, output_dir: str = "output/spec_agent") -> str:
    """Save project spec as a JSON file.

    Returns the path to the saved file.
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    json_path = path / "spec.json"
    json_path.write_text(to_json(spec))

    return str(json_path)
