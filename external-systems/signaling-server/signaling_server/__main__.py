"""Entry point for running signaling server as module."""

from __future__ import annotations

from .server import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())