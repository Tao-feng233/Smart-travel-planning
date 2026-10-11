"""Run the real asset initialization and login renderer with extra dependencies."""

from pathlib import Path
import subprocess
import sys


def test_login_versions_only_include_declared_resources(tmp_path):
    frontend = tmp_path / "frontend"
    files = {
        "core/client.js": "const ready = true;",
        "styles/base.css": "body {}",
        "node_modules/library/vendor.js": "const vendor = true;",
        "old-unused.js": "const abandoned = true;",
    }
    for name, content in files.items():
        file = frontend / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    (frontend / "index.html").write_text(
        '<script defer src="/assets/core/client.js"></script>'
        '<link rel="stylesheet" href="/assets/styles/base.css">',
        encoding="utf-8",
    )
    script = """
from pathlib import Path
import sys
from app.core import config
config.ROOT=Path(sys.argv[1])
from app.api import security, system
assert set(security.ASSET_VERSIONS)=={'core/client.js','styles/base.css'}, list(security.ASSET_VERSIONS)
html=system.home().body.decode()
for name,version in security.ASSET_VERSIONS.items():
    assert '/assets/'+name+'?v='+version in html
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
