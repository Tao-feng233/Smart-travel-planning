"""修复 DSH 会话文件里会让「对话」视图渲染为空白的事件（只读诊断 + 可控重写）。

根因：DSH 在运行被中止时会写入 data.reason = null 的 turn/end，
而它自己的 chat 视图代码多处直接读 event.data.reason.kind（无空值判断），
解析到该事件即抛异常，于是整个对话面板为空（轨迹视图不受影响）。

用法：
    python _dsh_repair.py scan  <file>...                 # 只读：报告 null reason 等异常
    python _dsh_repair.py copy  <file> <new-id> <title>   # 生成修复后的副本（不动原文件）
    python _dsh_repair.py inplace <file>                  # 原地修复（必须先完全退出 DSH！）
    python _dsh_repair.py register <session-id>           # 把会话登记进 旅游推荐 工作区
"""
import io
import json
import os
import re
import shutil
import sys
import time
import uuid

import zstandard

WS_DIR = r"C:\Users\HP\.dsh\sessions\--C-Users-HP-Desktop-~65C5~6E38~63A8~8350--"
WORKSPACE_JSON = r"C:\Users\HP\.dsh\storages\workspace.json"
WORKSPACE_ID = "5dc0cb3f-f6a3-4380-82da-863c5a64980f"
CWD = "C:\\Users\\HP\\Desktop\\旅游推荐"


def read_lines(path):
    raw = open(path, "rb").read()
    dctx = zstandard.ZstdDecompressor()
    out = bytearray()
    with dctx.stream_reader(io.BytesIO(raw), read_across_frames=True) as reader:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out += chunk
    return [l for l in out.decode("utf-8").split("\n") if l.strip()]


def write_lines(path, lines):
    cctx = zstandard.ZstdCompressor(level=3)
    tmp = path + ".tmp-repair"
    with open(tmp, "wb") as f:
        for line in lines:
            f.write(cctx.compress(line.encode("utf-8") + b"\n"))
    os.replace(tmp, path)


def fix_null_reasons(lines):
    """把 '"reason":null' 改成合法的 '"reason":{"kind":"interrupted"}'。"""
    pattern = re.compile(r'"reason"\s*:\s*null')
    fixed = []
    count = 0
    for line in lines:
        if pattern.search(line):
            obj = json.loads(line)
            if obj.get("type") == "turn/end" and (obj.get("data") or {}).get("reason") is None:
                line = pattern.sub('"reason":{"kind":"interrupted"}', line)
                count += 1
        fixed.append(line)
    return fixed, count


def seq_of(lines):
    last = 0
    for line in lines[1:]:
        obj = json.loads(line)
        if isinstance(obj.get("seq"), int):
            last = obj["seq"]
    return last


def scan(paths):
    for path in paths:
        lines = read_lines(path)
        events = [json.loads(l) for l in lines[1:]]
        bad = [e for e in events if e.get("type") == "turn/end" and not (e.get("data") or {}).get("reason")]
        seqs = [e["seq"] for e in events if "seq" in e]
        print("%s\n  事件=%d 序号连续=%s null-reason 的 turn/end=%s"
              % (path, len(events), seqs == list(range(len(seqs))), [(e.get("seq"), e.get("time")) for e in bad]))


def make_copy(src, new_id, title):
    lines = read_lines(src)
    lines, fixed = fix_null_reasons(lines)
    header = json.loads(lines[0])
    new_header = dict(header)
    new_header["id"] = new_id
    new_header["createdAt"] = int(time.time() * 1000)
    new_header["cwd"] = CWD
    new_header["isSeeded"] = False
    lines[0] = json.dumps(new_header, ensure_ascii=False, separators=(",", ": "))
    lines.append(json.dumps({
        "type": "session/title", "seq": seq_of(lines) + 1, "time": int(time.time() * 1000),
        "data": {"title": title, "messageSeqs": [9],
                 "source": {"kind": "provider", "provider": "session-title-first-prompt-llm",
                            "model": {"provider": "deepseek-official", "model": "deepseek-flash"}}},
    }, ensure_ascii=False, separators=(",", ": ")))
    dest_dir = os.path.join(WS_DIR, new_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "session.v4.jsonl.zstd")
    write_lines(dest, lines)
    print("副本已写出: %s\n  事件=%d（修正 reason=null 共 %d 处）" % (dest, len(lines) - 1, fixed))
    return dest


def repair_inplace(path):
    backup = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, backup)
    lines, fixed = fix_null_reasons(read_lines(path))
    write_lines(path, lines)
    print("原地修复完成: %s\n  修正 %d 处，备份: %s" % (path, fixed, backup))


def register(session_id):
    backup = WORKSPACE_JSON + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    if not os.path.exists(backup):
        shutil.copy2(WORKSPACE_JSON, backup)
    data = json.load(open(WORKSPACE_JSON, encoding="utf-8"))
    lst = data["tables"]["workspaces"][WORKSPACE_ID]["sessionIds"]
    if session_id in lst:
        lst.remove(session_id)
    lst.insert(0, session_id)
    json.dump(data, open(WORKSPACE_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("已登记进工作区: %s（备份 %s）" % (session_id, backup))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "scan":
        scan(args)
    elif cmd == "copy":
        make_copy(args[0], args[1], args[2])
    elif cmd == "inplace":
        repair_inplace(args[0])
    elif cmd == "register":
        register(args[0])
    else:
        print(__doc__)
