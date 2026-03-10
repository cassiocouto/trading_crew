# Dashboard Demo GIF Capture

Reproducible script that drives a headless browser through the dashboard pages and
produces an optimized animated GIF suitable for the project README or blog articles.

## Prerequisites

1. **Playwright** (Python):

   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Pillow** — used to stitch screenshots into an animated GIF (already included in the project dependencies).

3. The dashboard must be running (`make start`) before you execute the script.

## Usage

```bash
uv run python scripts/capture_demo/capture.py
```

Output: `docs/demo.gif` (created automatically).

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | `http://localhost:3000` | Dashboard base URL |
| `--output` | `docs/demo.gif` | Output GIF path |
| `--fps` | `5` | Frames per second |
| `--width` | `1280` | Viewport width in pixels |
| `--height` | `720` | Viewport height in pixels |
| `--dark` | off | Toggle dark mode before capturing |

### Examples

Capture in dark mode at 1080p:

```bash
uv run python scripts/capture_demo/capture.py --dark --width 1920 --height 1080
```

Custom output path and higher frame rate:

```bash
uv run python scripts/capture_demo/capture.py --output assets/preview.gif --fps 10
```
