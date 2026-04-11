"""Tests for interactions router.

The collision endpoints were removed in the unified behavior redesign.
Behavior evaluation now happens via spawn integration and WS state_changed.
This file is retained as a placeholder for future interaction endpoint tests.
"""

from __future__ import annotations

from app.routers import interactions


def test_router_exists() -> None:
    """Verify the interactions router is importable and has the expected prefix."""
    assert interactions.router.prefix == "/api/sessions/{session_id}/interactions"
