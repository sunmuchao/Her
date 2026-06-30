from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .build import all_job_ids, create_blocking_scheduler, run_job_once
from .config import SchedulerSettings
from .health_check import SchedulerHealthChecker

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _run_health_server(port: int = 9090) -> None:
    """运行健康检查 HTTP 服务"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                checker = SchedulerHealthChecker()
                health_status = checker.full_health_check()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(checker.to_json().encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # 避免健康检查日志过多
            if "/health" not in args[0]:
                logging.getLogger(__name__).info(format, *args)

    # 绑定到 0.0.0.0，允许 Docker 健康检查从容器外部访问
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.getLogger(__name__).info(f"Health check server started on http://0.0.0.0:{port}/health")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified task scheduler for Her recommendation & matchmaking.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    parser.add_argument("--health-port", type=int, default=9090, help="Health check HTTP server port.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the blocking scheduler until interrupted.")
    p_run.set_defaults(handler=_cmd_run)

    p_list = sub.add_parser("list", help="Print job ids that would be registered for current env.")
    p_list.set_defaults(handler=_cmd_list)

    p_once = sub.add_parser("run-once", help="Execute a single job and exit.")
    p_once.add_argument("job_id", help="Job id, e.g. recommendation.refresh_saved_searches")
    p_once.set_defaults(handler=_cmd_run_once)

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _load_dotenv()
    settings = SchedulerSettings.from_environ()
    return int(args.handler(args, settings))


def _cmd_run(args: argparse.Namespace, settings: SchedulerSettings) -> int:
    # 启动健康检查服务
    _run_health_server(args.health_port)

    scheduler = create_blocking_scheduler(settings)
    logging.getLogger(__name__).info("scheduler started; Ctrl+C to stop")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


def _cmd_list(_args: argparse.Namespace, settings: SchedulerSettings) -> int:
    for job_id in all_job_ids(settings):
        print(job_id)
    if not all_job_ids(settings):
        print(
            "No jobs (set HER_SCHED_RECOMMENDATION_DB and/or HER_SCHED_MATCHMAKING_DB).",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_run_once(args: argparse.Namespace, settings: SchedulerSettings) -> int:
    try:
        run_job_once(args.job_id, settings)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
