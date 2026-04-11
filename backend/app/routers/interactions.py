"""Interactions router — placeholder after collision system removal.

Collision endpoints were removed in the unified behavior redesign.
Behavior evaluation now happens via spawn integration and WS state_changed.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/sessions/{session_id}/interactions", tags=["interactions"])
