#!/usr/bin/env python3
"""Stamp a release version onto asset URLs in a deployed copy of the site.

Browsers cache scripts. After a release, a page can pair a new script with
an older cached copy of a module it imports, and break. Adding ?v=<version>
to every relative .js, .css, and content .json URL makes each release load
a matching set.

Run it on the copy being deployed, never on the source:

    python3 tools/stamp.py <deployed-site-dir> <version>

The source stays unstamped, so the site still runs with no build step.
"""

from __future__ import annotations

import pathlib
import re
import sys

# src="../assets/js/loop.js" and href="../assets/css/site.css" in HTML.
HTML_ASSET = re.compile(r'''((?:src|href)=")((?!https?:|//|#)[^"?]+\.(?:js|css))(")''')
# import ... from "./scene.js" and import("./x.js") in JS and inline modules.
JS_IMPORT = re.compile(r'''((?:from|import)\s*\(?\s*["'])(\.{1,2}/[^"'?]+\.js)(["'])''')
# The content version constant in common.js.
VERSION_CONST = re.compile(r'const ASSET_VERSION = "[^"]*";')


def stamp(site: pathlib.Path, version: str) -> int:
    changed = 0
    for path in site.rglob("*"):
        if path.suffix not in {".html", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        new = JS_IMPORT.sub(rf"\g<1>\g<2>?v={version}\g<3>", text)
        if path.suffix == ".html":
            new = HTML_ASSET.sub(rf"\g<1>\g<2>?v={version}\g<3>", new)
        new = VERSION_CONST.sub(f'const ASSET_VERSION = "{version}";', new)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    site, version = pathlib.Path(sys.argv[1]), sys.argv[2]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        print(f"stamp.py: version must be letters, digits, '.', '_' or '-': {version!r}")
        return 2
    count = stamp(site, version)
    print(f"stamp.py: stamped {count} file(s) in {site} with v={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
