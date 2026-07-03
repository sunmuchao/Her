"""
多线程 WSGI 服务器启动脚本
替换单线程的 wsgiref.simple_server，避免死锁问题
"""

from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn


def _load_repo_root_dotenv() -> None:
    """Load monorepo ``Her/.env``. Uses ``override=True`` so file wins over stale shell exports."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "match_domain").is_dir() and (p / "pyproject.toml").is_file():
            env_path = p / ".env"
            if env_path.is_file():
                # Preserve explicitly injected runtime env (for Docker/Compose).
                load_dotenv(env_path, override=False)
            return


_load_repo_root_dotenv()

from .app import application
from .logging_setup import configure_gateway_logging


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """多线程 WSGI 服务器，每个请求在独立线程中处理"""
    daemon_threads = True  # 线程随主进程退出
    timeout = 30  # 每个请求最长处理时间（秒）


def main() -> None:
    parser = argparse.ArgumentParser(description="Partner recommendation + matchmaking HTTP / JSON-RPC gateway")
    parser.add_argument("--host", default=os.environ.get("PARTNER_HTTP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PARTNER_HTTP_PORT", "8765")))
    parser.add_argument("--threads", type=int, default=int(os.environ.get("PARTNER_GATEWAY_THREADS", "8")))
    parser.add_argument("--log-level", default=os.environ.get("PARTNER_GATEWAY_LOG_LEVEL"))
    parser.add_argument("--log-file", default=os.environ.get("PARTNER_GATEWAY_LOG_FILE"))
    args = parser.parse_args()

    configure_gateway_logging(log_level=args.log_level, log_file=args.log_file)

    # 使用多线程服务器替代单线程
    httpd = make_server(args.host, args.port, application, ThreadingWSGIServer)

    logging.getLogger(__name__).info(
        "Partner HTTP gateway (多线程) at http://%s:%s (REST /v1/..., JSON-RPC POST /jsonrpc)",
        args.host,
        args.port,
    )
    logging.getLogger(__name__).info("使用 %s 个线程处理请求", args.threads)

    httpd.serve_forever()


if __name__ == "__main__":
    main()
