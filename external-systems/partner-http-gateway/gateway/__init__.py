"""HTTP + JSON-RPC gateway for partner recommendation and matchmaking systems."""

from .app import application, make_application

__all__ = ["application", "make_application"]
