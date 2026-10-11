"""Version the scripts and styles declared by the application shell."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        url = attrs.get("src") if tag == "script" else None
        if tag == "link" and "stylesheet" in attrs.get("rel", "").split():
            url = attrs.get("href")
        if url and url.startswith("/assets/"):
            self.paths.add(urlsplit(url).path.removeprefix("/assets/"))


def asset_versions(frontend: Path):
    page = PageAssets()
    page.feed((frontend / "index.html").read_text(encoding="utf-8"))
    return {
        path: hashlib.sha256((frontend / path).read_bytes()).hexdigest()[:12]
        for path in sorted(page.paths)
    }
