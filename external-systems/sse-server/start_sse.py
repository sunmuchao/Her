#!/usr/bin/env python
"""SSE Server startup script for Docker container."""

import sys
import logging

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
    force=True,
)

logger = logging.getLogger("sse_startup")

def main():
    """Start SSE server."""
    import os

    host = os.environ.get("SSE_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SSE_SERVER_PORT", "8081"))

    logger.info(f"=== SSE Server Startup ===")
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Working dir: {os.getcwd()}")

    try:
        from sse_server.server import SSEServer
        import asyncio

        logger.info("Creating SSE server instance...")
        server = SSEServer(host=host, port=port)

        logger.info("Starting async event loop...")
        asyncio.run(server.run_forever())

    except Exception as e:
        logger.error(f"Failed to start SSE server: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()