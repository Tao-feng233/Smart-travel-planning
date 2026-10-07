"""Start the local service, or reuse this project's healthy running service."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8767/'
PROJECT_ID = hashlib.sha256(str(ROOT.resolve()).casefold().encode()).hexdigest()[:16]


def running_service():
    try:
        with build_opener(ProxyHandler({})).open(URL + 'api/healthz', timeout=3) as response:
            health = json.load(response)
        return (health.get('status') == 'ok' and health.get('service') == 'shitu'
                and health.get('project_id') == PROJECT_ID)
    except (OSError, ValueError):
        return False


def main():
    if running_service():
        print('识途已经在运行，无需重复启动。')
        print('请打开 ' + URL + '，旧页面请按 Ctrl+F5 刷新。')
        return 0
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', 8767)) == 0:
            print('8767 端口已被占用，但未确认是本项目的正常服务。')
            print('请查看原启动窗口；如为旧版识途，在原窗口按 Ctrl+C 后重新启动。')
            print('没有停止占用端口的进程，以免影响其他程序。')
            return 1
    print('识途启动后访问 ' + URL, flush=True)
    print('保持此窗口开启；按 Ctrl+C 停止服务。', flush=True)
    try:
        return subprocess.call([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                '--host', '127.0.0.1', '--port', '8767', '--no-access-log'], cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
