"""Capture an animated GIF of the dashboard for documentation.

Drives a headless Chromium browser through each dashboard page,
takes a screenshot at each step, and stitches them into an
optimized GIF via Pillow.

Run with:  uv run python scripts/capture_demo/capture.py
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

PAGES: list[tuple[str, str]] = [
    ("/", "overview"),
    ("/markets", "markets"),
    ("/orders", "orders"),
    ("/signals", "signals"),
    ("/history", "history"),
    ("/agents", "agents"),
    ("/controls", "controls"),
]

DWELL_SECONDS = 3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture a dashboard demo GIF")
    p.add_argument("--url", default="http://localhost:3000", help="Dashboard base URL")
    p.add_argument("--output", default="docs/demo.gif", help="Output GIF path")
    p.add_argument("--fps", type=int, default=5, help="Frames per second")
    p.add_argument("--width", type=int, default=1280, help="Viewport width")
    p.add_argument("--height", type=int, default=720, help="Viewport height")
    p.add_argument("--dark", action="store_true", help="Enable dark mode before capturing")
    return p.parse_args()


def _toggle_dark(page) -> None:
    """Click the theme toggle button until dark mode is active."""
    for _ in range(3):
        toggle = page.locator("button[aria-label*='theme' i], button[aria-label*='Theme' i]").first
        if toggle.count():
            toggle.click()
            page.wait_for_timeout(500)
            if "dark" in (page.evaluate("document.documentElement.className") or ""):
                return
    print("WARNING: Could not activate dark mode -- continuing in current theme", file=sys.stderr)


def capture_frames(args: argparse.Namespace, tmpdir: Path) -> list[Path]:
    frames: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": args.width, "height": args.height})
        page = ctx.new_page()

        page.goto(args.url, wait_until="networkidle")

        if args.dark:
            _toggle_dark(page)

        frame_idx = 0
        for route, name in PAGES:
            page.goto(f"{args.url}{route}", wait_until="networkidle")
            page.wait_for_timeout(1500)

            n_frames = DWELL_SECONDS * args.fps
            interval_ms = 1000 // args.fps
            for _ in range(n_frames):
                fpath = tmpdir / f"frame_{frame_idx:05d}.png"
                page.screenshot(path=str(fpath))
                frames.append(fpath)
                frame_idx += 1
                page.wait_for_timeout(interval_ms)

            print(f"  [ok] {name:<12} ({n_frames} frames)")

        browser.close()
    return frames


def stitch_gif(frames: list[Path], args: argparse.Namespace) -> None:
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    duration_ms = 1000 // args.fps
    images = [Image.open(f) for f in frames]

    first = images[0].copy()
    first.save(
        str(out),
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )

    for img in images:
        img.close()

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nDone! GIF saved to {out}  ({size_mb:.1f} MB)")


def main() -> None:
    args = parse_args()
    print(f"Capturing dashboard at {args.url}  ({args.width}x{args.height})")

    with tempfile.TemporaryDirectory(prefix="demo_capture_") as tmpdir:
        frames = capture_frames(args, Path(tmpdir))
        if not frames:
            sys.exit("No frames captured -- is the dashboard running?")
        print(f"\nCaptured {len(frames)} frames, stitching GIF...")
        stitch_gif(frames, args)


if __name__ == "__main__":
    main()
