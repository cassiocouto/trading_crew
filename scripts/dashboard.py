"""Dashboard API launcher.

Starts the FastAPI dashboard server using uvicorn.

Usage:
    uv run python scripts/dashboard.py
    uv run python scripts/dashboard.py --host 127.0.0.1 --port 8080
    uv run python scripts/dashboard.py --reload   # development hot-reload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the src/ directory is on the path when running directly
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def main() -> None:
    import uvicorn

    from trading_crew.config.settings import get_settings

    settings = get_settings()

    parser = argparse.ArgumentParser(description="Trading Crew Dashboard API Server")
    parser.add_argument("--host", default=settings.dashboard_host, help="Bind host")
    parser.add_argument("--port", type=int, default=settings.dashboard_port, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    parser.add_argument("--log-level", default="info", help="Uvicorn log level")
    args = parser.parse_args()

    print(f"Starting Trading Crew Dashboard API on http://{args.host}:{args.port}")
    print(f"WebSocket endpoint: ws://{args.host}:{args.port}/ws/events")
    if settings.dashboard_api_key:
        print("API key authentication: ENABLED")
    else:
        print("API key authentication: disabled (set DASHBOARD_API_KEY to enable)")

    uvicorn.run(
        "trading_crew.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
