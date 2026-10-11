"""Emit one pre-scanned public upload chunk for the GitHub connector."""

from pathlib import Path
import sys, re

sys.stdout.reconfigure(encoding="utf-8")
name = sys.argv[1]
if not re.fullmatch(r"(?:queue\.json|text-\d{3}\.json|blob-\d{3}-\d{3}\.txt)", name):
    raise SystemExit("Invalid upload chunk")
base = Path(__file__).resolve().parents[2] / "data/runtime/repository-migration/upload"
sys.stdout.write((base / name).read_text(encoding="utf-8"))
