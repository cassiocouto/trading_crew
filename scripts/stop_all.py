#!/usr/bin/env python3
"""Force-stop any lingering Trading Crew services (ports 3000, 8000) and
remove the Next.js dev lock file so a clean restart is possible.

Usage:
    uv run python scripts/stop_all.py
    make stop
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "dashboard" / ".next" / "dev" / "lock"

PORTS = [3000, 8000]

_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _pids_on_port_win32(port: int) -> set[int]:
    """Return PIDs listening on *port* (Windows)."""
    try:
        out = subprocess.check_output(
            "netstat -ano",
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return set()

    pids: set[int] = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                with contextlib.suppress(ValueError):
                    pids.add(int(parts[-1]))
    return pids


def _pids_on_port_unix(port: int) -> set[int]:
    """Return PIDs listening on *port* (Linux / macOS)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return {int(p) for p in out.split() if p.strip().isdigit()}


def _kill(pid: int) -> bool:
    """Force-kill a process by PID. Returns True on success."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            os.kill(pid, 9)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main() -> None:
    pids_on_port = _pids_on_port_win32 if sys.platform == "win32" else _pids_on_port_unix

    killed: set[int] = set()
    for port in PORTS:
        for pid in pids_on_port(port):
            if pid in killed or pid == os.getpid():
                continue
            if _kill(pid):
                print(f"  {_RED}Killed PID {pid}{_RESET} {_DIM}(port {port}){_RESET}")
                killed.add(pid)

    if LOCK_FILE.exists():
        LOCK_FILE.unlink(missing_ok=True)
        print(f"  {_RED}Removed{_RESET} {_DIM}{LOCK_FILE}{_RESET}")

    if not killed and not LOCK_FILE.exists():
        print(f"  {_GREEN}Nothing to clean up — ports {PORTS} are free.{_RESET}")
    else:
        print(f"\n  {_GREEN}{_BOLD}Done.{_RESET} Safe to run {_BOLD}make start{_RESET} now.")


if __name__ == "__main__":
    main()
