#!/usr/bin/env python3
"""
Keeps the Mongolia WHM check running inside ONE GitHub Actions job.

GitHub's cron schedule is throttled (runs were ~35 min apart instead of 5), so
instead of waiting for the next scheduled run, this calls check_mongolia.main()
every POLL_SECONDS for RUN_MINUTES. The next scheduled run queues behind this one
(see `concurrency` in monitor.yml), so there is no gap in coverage.

Manual "Run workflow" uses RUN_MINUTES=0, which means a single check.
"""
import os
import sys
import time
import traceback

import check_mongolia

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "60"))
RUN_MINUTES = float(os.environ.get("RUN_MINUTES", "110"))

# Checks happen every ~60 s, so 10 failures in a row is ~10 minutes before we warn.
check_mongolia.FAILURE_ALERT_AFTER = 10


def main() -> int:
    deadline = time.monotonic() + RUN_MINUTES * 60
    n = 0
    while True:
        n += 1
        started = time.monotonic()
        print(f"--- check #{n} ---", flush=True)
        try:
            rc = check_mongolia.main()
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
        except Exception:  # noqa: BLE001 - never let one bad check kill the loop
            traceback.print_exc()
            rc = None
        sys.stdout.flush()
        if n == 1 and rc:  # config problem (missing token / no chat): fail fast like before
            return rc
        os.environ["SEND_TEST"] = "false"  # test message only on the first check
        pause = max(POLL_SECONDS - (time.monotonic() - started), 5)
        if time.monotonic() + pause >= deadline:
            return 0
        time.sleep(pause)


if __name__ == "__main__":
    sys.exit(main())
