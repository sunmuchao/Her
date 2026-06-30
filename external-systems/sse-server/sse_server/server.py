"""SSE Server for real-time chat message push."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from aiohttp import web

from .config import config
from .connection_manager import ConnectionManager
from .handlers import SSEHandlers, setup_routes

logger = logging.getLogger(__name__)


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """CORS middleware to allow cross-origin requests from frontend."""
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        response = web.Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Max-Age"] = "86400"  # 24 hours
        return response

    # Handle actual request
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc

    # Add CORS headers to all responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

    return response


class SSEServer:
    """SSE Server for real-time message push."""

    def __init__(
        self,
        host: str = config.HOST,
        port: int = config.PORT,
    ) -> None:
        """Initialize SSE server.

        Args:
            host: Server host
            port: Server port
        """
        self.host = host
        self.port = port
        self.connection_manager = ConnectionManager()
        self.handlers = SSEHandlers(self.connection_manager)
        self.app = web.Application(middlewares=[cors_middleware])
        self._runner = None
        self._site = None

        # Setup routes
        setup_routes(self.app, self.handlers)

        # Setup logging
        logging.basicConfig(
            level=config.LOG_LEVEL,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )

    async def start(self) -> None:
        """Start the SSE server."""
        logger.info(f"Starting SSE server on {self.host}:{self.port}")

        self._runner = web.AppRunner(self.app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        logger.info(f"SSE server started on http://{self.host}:{self.port}")
        logger.info(f"  SSE endpoint: http://{self.host}:{self.port}/sse/chat/{'{caseId}'}")
        logger.info(f"  Push endpoint: http://{self.host}:{self.port}/internal/push")
        logger.info(f"  Health check: http://{self.host}:{self.port}/health")
        logger.info(f"  Stats: http://{self.host}:{self.port}/internal/stats")

    async def stop(self) -> None:
        """Stop the SSE server."""
        logger.info("Stopping SSE server...")

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        logger.info("SSE server stopped")

    async def run_forever(self) -> None:
        """Run the server forever."""
        await self.start()

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()

        def signal_handler() -> None:
            logger.info("Received shutdown signal")
            loop.create_task(self.stop())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

        # Wait forever
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour, loop forever
        except asyncio.CancelledError:
            logger.info("Server loop cancelled")
        finally:
            await self.stop()


async def main(host: str, port: int) -> None:
    """Main entry point.

    Args:
        host: Server host
        port: Server port
    """
    server = SSEServer(host=host, port=port)
    await server.run_forever()


def run() -> None:
    """Run SSE server from command line."""
    parser = argparse.ArgumentParser(description="SSE Server for chat message push")
    parser.add_argument(
        "--host",
        type=str,
        default=config.HOST,
        help="Server host (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.PORT,
        help="Server port (default: %(default)s)",
    )

    args = parser.parse_args()

    # Setup logging first
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    logger.info(f"Starting SSE server with args: host={args.host}, port={args.port}")

    # Create and run server directly
    server = SSEServer(host=args.host, port=args.port)

    try:
        # Use uvloop for better performance if available
        try:
            import uvloop
            uvloop.install()
            logger.info("Using uvloop for better async performance")
        except ImportError:
            logger.info("uvloop not available, using default asyncio")

        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
    except Exception as e:
        logger.error(f"SSE server crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
