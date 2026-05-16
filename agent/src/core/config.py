"""Centralised data directory configuration.

All persistent data paths are derived from a single ``DATA_DIR`` environment
variable.  Defaults to ``<project_root>/run/`` for local development and is
overridden to ``/data`` inside Docker containers.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def get_data_dir() -> Path:
    """Return the unified data root, creating it if necessary."""
    d = Path(os.environ.get("DATA_DIR", str(_PROJECT_ROOT / "run")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_runs_dir() -> Path:
    d = get_data_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_sessions_dir() -> Path:
    d = get_data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_swarm_dir() -> Path:
    d = get_data_dir() / "swarm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_uploads_dir() -> Path:
    d = get_data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_memory_dir() -> Path:
    d = get_data_dir() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_skills_dir() -> Path:
    d = get_data_dir() / "skills" / "user"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_shadow_dir() -> Path:
    d = get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_fonts_dir() -> Path:
    d = get_data_dir() / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d
