#!/usr/bin/env python3
"""Serve the site locally for preview and teaching.

Browsers refuse to load content/*.json from file:// URLs, so the site must
be opened through a web server. This is a thin wrapper around the standard
library's http.server.

"Go deeper" links point to ../course/ beside the site. When that folder
exists, the server serves the site's parent directory so those links work,
and prints the site's address within it.

Usage:
    python3 tools/serve.py              # http://127.0.0.1:8000
    python3 tools/serve.py --port 9000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import pathlib

SITE_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Explicit types: some systems map .js to text/plain, which breaks ES modules.
EXTRA_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".css": "text/css",
    ".svg": "image/svg+xml",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES}

    def end_headers(self) -> None:
        # Always serve fresh files so edits to content show on reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1", help="address to listen on (default: localhost only)")
    args = parser.parse_args()

    root, path = SITE_ROOT, ""
    if (SITE_ROOT.parent / "course").is_dir():
        root, path = SITE_ROOT.parent, f"{SITE_ROOT.name}/"

    handler = functools.partial(Handler, directory=str(root))
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Serving {root}")
        print(f"Open http://{args.bind}:{args.port}/{path}  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
