"""DSH 会话文件分析（只读）。

用法:  python _dsh_analyze.py [session-file ...]
不带参数时分析 旅游推荐 工作区下的全部会话文件。
"""
import collections
import datetime
import io
import json
import os
import sys

import zstandard

WS_DIR = r"C:\Users\HP\.dsh\sessions\--C-Users-HP-Desktop-~65C5~6E38~63A8~8350--"


def load(path):
    raw = open(path, "rb").read()
    dctx = zstandard.ZstdDecompressor()
    out = bytearray()
    with dctx.stream_reader(io.BytesIO(raw), read_across_frames=True) as reader:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out += chunk
    lines = [l for l in out.decode("utf-8", "replace").split("\n") if l.strip()]
    return out, [(len(l), json.loads(l)) for l in lines]


def ts(ms):
    try:
        return datetime.datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M:%S")
    except Exception:
        return "-"


def report(name, path, tail=10):
    decompressed, events = load(path)
    print("=" * 96)
    print("%s | %s bytes | %d events | mtime %s" % (
        name, os.path.getsize(path), len(events) - 1,
        datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%m-%d %H:%M:%S")))
    print("  decompressed: %.2f MB" % (len(decompressed) / 1048576))
    print("  types:", dict(collections.Counter(e.get("type") for _, e in events).most_common()))
    ops = collections.Counter()
    repl = []
    for _, e in events:
        op = e.get("surfaceOp")
        if op is None:
            continue
        if op == "append":
            ops["append"] += 1
        else:
            ops["REPLACE(%s)" % e.get("type")] += 1
            repl.append((e.get("seq"), e.get("type"), json.dumps(op, ensure_ascii=False)[:100]))
    print("  surfaceOps:", dict(ops))
    for row in repl[:10]:
        print("     replace:", row)
    print("  last %d:" % tail)
    for n, e in events[-tail:]:
        extra = ""
        d = e.get("data") or {}
        if e.get("type") == "assistant/message":
            blocks = [(c.get("type"), len(c.get("text", ""))) for c in (d.get("message") or {}).get("content", [])]
            extra = "turn=%s step=%s blocks=%s" % (d.get("turn"), d.get("step"), blocks)
        elif e.get("type") == "user/message":
            extra = "src=%s" % ((d.get("source") or {}).get("kind"),)
        elif e.get("type") == "tool/call":
            extra = "name=%s" % d.get("name")
        elif e.get("type") == "turn/end":
            extra = "reason=%s" % json.dumps(d.get("reason"), ensure_ascii=False)
        elif e.get("type") == "agent/inbox/spliced":
            extra = json.dumps(d, ensure_ascii=False)[:120]
        print("     %-40s seq=%-5s %s %6d B %s" % (e.get("type"), e.get("seq"), ts(e.get("time")), n, extra))
    biggest = sorted(events, key=lambda x: -x[0])[:5]
    print("  largest events:", [(e.get("type"), n, ts(e.get("time"))) for n, e in biggest])
    return events


if __name__ == "__main__":
    paths = sys.argv[1:]
    if not paths:
        paths = sorted(
            os.path.join(dp, f)
            for dp, _, fns in os.walk(WS_DIR)
            for f in fns
            if f.startswith("session")
        )
    for p in paths:
        if p.endswith(".zstd"):
            report(os.path.basename(os.path.dirname(p)), p)
