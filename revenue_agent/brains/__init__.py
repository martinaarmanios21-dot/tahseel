"""Brains decide; they never act. Every decision they return goes through the guardrails."""

from __future__ import annotations

import sqlite3

from ..config import Settings, get_settings
from .base import Brain, BrainError, BrainResult


def make_brain(name: str, conn: sqlite3.Connection, settings: Settings | None = None) -> Brain:
    settings = settings or get_settings()
    if name == "offline":
        from .offline import OfflineBrain
        return OfflineBrain()
    if name == "api":
        from .api import ApiBrain
        return ApiBrain(conn, settings)
    if name == "hermes":
        from .hermes import HermesBrain
        return HermesBrain(conn, settings)
    raise ValueError(f"unknown engine {name!r} (use offline | api | hermes)")


__all__ = ["Brain", "BrainError", "BrainResult", "make_brain"]
