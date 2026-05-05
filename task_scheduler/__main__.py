from __future__ import annotations

import argparse
import logging
import sys

from .build import all_job_ids, create_blocking_scheduler, run_job_once
from .config import SchedulerSettings


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified task scheduler for Her recommendation & matchmaking.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
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
    settings = SchedulerSettings.from_environ()
    return int(args.handler(args, settings))


def _cmd_run(_args: argparse.Namespace, settings: SchedulerSettings) -> int:
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
