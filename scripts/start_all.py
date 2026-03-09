#!/usr/bin/env python3
"""Start the full Trading Crew stack: trading bot + FastAPI API + Next.js UI.

All three processes run concurrently with color-coded prefixed output.
Ctrl-C stops all of them cleanly.

Usage:
    uv run python scripts/start_all.py               # paper mode (default)
    uv run python scripts/start_all.py --mode live   # live mode (5-second warning)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"


def _stream(proc: subprocess.Popen[str], label: str, color: str) -> None:
    """Read a process's stdout line-by-line and write it with a colored prefix."""
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        sys.stdout.write(f"{color}{_BOLD}[{label}]{_RESET} {line}")
        sys.stdout.flush()


def _stop_all(procs: list[tuple[str, subprocess.Popen[str]]]) -> None:
    """Terminate all running processes; kill any that don't exit within 5 s."""
    for _label, p in procs:
        if p.poll() is None:
            p.terminate()
    for label, p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"{_RED}[{label}] did not exit cleanly — killing.{_RESET}")
            p.kill()
            p.wait()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start trading bot + FastAPI + Next.js dashboard in one command.",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    args = parser.parse_args()

    if args.mode == "live":
        border = "=" * 62
        print(f"\n{_RED}{_BOLD}{border}")
        print("  WARNING: LIVE MODE — real orders will be placed on your exchange!")
        print("  Make sure .env has correct exchange credentials and trading_mode")
        print("  in settings.yaml is irrelevant — this command forces LIVE.")
        print("  Press Ctrl+C within 5 seconds to abort.")
        print(f"{border}{_RESET}\n")
        try:
            for remaining in range(5, 0, -1):
                sys.stdout.write(f"\r  Starting in {remaining}s ... ")
                sys.stdout.flush()
                time.sleep(1)
            print()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)

    env = {
        **os.environ,
        "TRADING_MODE": args.mode,
        "PYTHONUNBUFFERED": "1",
    }
    npm = "npm.cmd" if sys.platform == "win32" else "npm"

    specs: list[tuple[str, list[str], str, str]] = [
        (" bot", ["uv", "run", "trading-crew"], _CYAN, str(ROOT)),
        (" api", ["uv", "run", "python", "scripts/dashboard.py"], _GREEN, str(ROOT)),
        ("  ui", [npm, "run", "dev"], _YELLOW, str(ROOT / "dashboard")),
    ]

    procs: list[tuple[str, subprocess.Popen[str]]] = []

    try:
        print()
        for label, cmd, color, cwd in specs:
            p = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            procs.append((label, p))
            t = threading.Thread(target=_stream, args=(p, label, color), daemon=True)
            t.start()
            print(f"  {color}{_BOLD}[{label}]{_RESET} started  {_DIM}PID {p.pid}{_RESET}")

        mode_label = (
            f"{_RED}{_BOLD}LIVE{_RESET}" if args.mode == "live" else f"{_CYAN}{_BOLD}paper{_RESET}"
        )
        print(f"\n  Mode: {mode_label}   Dashboard → {_BOLD}http://localhost:3000{_RESET}")
        print(f"  {_DIM}Press Ctrl+C to stop all services.{_RESET}\n")
        print("-" * 62)

        # Block until any process exits unexpectedly
        while all(p.poll() is None for _, p in procs):
            time.sleep(0.5)

        # Report which one died
        for label, p in procs:
            if p.poll() is not None:
                print(f"\n{_RED}[{label}] exited unexpectedly with code {p.returncode}{_RESET}")

    except KeyboardInterrupt:
        print(f"\n{_BOLD}Shutting down...{_RESET}")
    finally:
        _stop_all(procs)
        print("All services stopped.")


if __name__ == "__main__":
    main()
