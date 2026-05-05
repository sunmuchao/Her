"""Run the gateway with: python -m gateway (from external-systems/partner-http-gateway)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from wsgiref.simple_server import make_server


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
                load_dotenv(env_path, override=True)
            return


_load_repo_root_dotenv()

from .app import application


def main() -> None:
    parser = argparse.ArgumentParser(description="Partner recommendation + matchmaking HTTP / JSON-RPC gateway")
    parser.add_argument("--host", default=os.environ.get("PARTNER_HTTP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PARTNER_HTTP_PORT", "8765")))
    args = parser.parse_args()
    httpd = make_server(args.host, args.port, application)
    print(f"Partner HTTP gateway at http://{args.host}:{args.port} (REST /v1/..., JSON-RPC POST /jsonrpc)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
