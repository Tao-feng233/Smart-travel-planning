"""Refresh checked public-source metadata and divide connector input into bounded chunks."""

from pathlib import Path
import json, base64, hashlib, shutil
from prepare_repository_migration import ROOT, STAGE, scan

root = ROOT / "data/runtime/repository-migration"
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
shutil.copy2(
    ROOT / "tests/test_interaction_v5.py", STAGE / "tests/test_interaction_v5.py"
)
shutil.copy2(ROOT / "tests/test_accounts.py", STAGE / "tests/test_accounts.py")
files = [STAGE / name for name in manifest["files"]]
scan(files)
for name in manifest["files"]:
    data = (STAGE / name).read_bytes()
    manifest["files"][name] = {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha": hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest(),
    }
manifest["total_bytes"] = sum(v["size"] for v in manifest["files"].values())
(root / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
queue = root / "upload"
queue.mkdir(exist_ok=True)
texts = []
blobs = []
for name, info in manifest["files"].items():
    data = (STAGE / name).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    item = {"path": name, "mode": "100644", "type": "blob"}
    if (
        text is not None
        and len(json.dumps({**item, "content": text}, ensure_ascii=False)) < 18000
    ):
        texts.append({**item, "content": text})
    else:
        b64 = base64.b64encode(data).decode("ascii")
        chunks = []
        for i in range(0, len(b64), 20000):
            chunk = f"blob-{len(blobs):03}-{i // 20000:03}.txt"
            (queue / chunk).write_text(b64[i : i + 20000], encoding="ascii")
            chunks.append(chunk)
        blobs.append(
            {
                **item,
                "encoding": "base64",
                "chunks": chunks,
                "size": len(data),
                "expected_sha": info["git_blob_sha"],
            }
        )
batches = []
batch = []
for item in texts:
    if batch and len(json.dumps(batch + [item], ensure_ascii=False)) > 18000:
        batches.append(batch)
        batch = []
    batch.append(item)
if batch:
    batches.append(batch)
for i, batch in enumerate(batches):
    (queue / f"text-{i:03}.json").write_text(
        json.dumps(batch, ensure_ascii=False), encoding="utf-8"
    )
meta = {
    "text_batches": [f"text-{i:03}.json" for i in range(len(batches))],
    "blobs": blobs,
    "file_count": len(manifest["files"]),
}
(queue / "queue.json").write_text(
    json.dumps(meta, ensure_ascii=False), encoding="utf-8"
)
print(
    json.dumps(
        {
            "files": meta["file_count"],
            "text_batches": len(batches),
            "blob_files": len(blobs),
            "secret_scan_passed": True,
        }
    )
)
