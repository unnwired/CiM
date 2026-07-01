"""Shared repo-root resolution for server unit tests (packages/server/tests layout)."""

from __future__ import annotations

from pathlib import Path

# packages/server/tests -> repo root is three levels up from server, four from tests file.
REPO_ROOT = Path(__file__).resolve().parents[3]
