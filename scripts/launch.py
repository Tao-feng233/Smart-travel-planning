"""Portable Windows launcher. Each extracted folder has its own data and lock."""
import argparse,hashlib,json,os,shutil,socket,subprocess,sys,time,webbrowser
from pathlib import Path
from urllib.request import build_opener,ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
PROJECT_ID=hashlib.sha256(str(ROOT.resolve()).casefold().encode()).hexdigest()[:16]
REQUIRED=('LLM_API_KEY','LLM_BASE_URL','LLM_MODEL','AMAP_API_KEY','QWEATHER_API_HOST','QWEATHER_API_KEY')

def configured():
    from dotenv import dotenv_values
    values=dotenv_values(ROOT/'.env',encoding='utf-8-sig')
    missing=[key for key in REQUIRED if not str(values.get(key) or '').strip()]
    if not any(str(values.get(key) or '').strip() for key in ('TUNIU_API_KEY',*(f'TUNIU_API_KEY_{i}' for i in range(1,5)))):missing.append('TUNIU_API_KEY_1（或 TUNIU_API_KEY）')
    return missing

def healthy(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/healthz',timeout=.6) as r:h=json.load(r)
        return h.get('status')=='ok' and h.get('service')=='shitu' and h.get('project_id')==PROJECT_ID
    except (OSError,ValueError):return False

def find_port(ports):
    free=[]
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(.2)
            occupied=probe.connect_ex(('127.0.0.1',port))==0
        if occupied:
            if healthy(port):return port,True
        else:free.append(port)
    return (free[0],False) if free else (None,False)

def main():
    parser=argparse.ArgumentParser(description='识途体验版启动器')
    parser.add_argument('--port',type=int);parser.add_argument('--no-browser',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--check-service',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.port is not None and not 1024<=args.port<=65535:parser.error('端口需在1024至65535之间')
    os.chdir(ROOT)
    if not (ROOT/'.env').exists():
        shutil.copyfile(ROOT/'.env.example',ROOT/'.env')
        print('首次启动：已创建接口配置文件 .env，请先填写配置。',flush=True)
        if not args.check and not args.no_browser:
            subprocess.run(['notepad.exe',str(ROOT/'.env')],check=False)
    missing=configured()
    if missing:
        print('缺少接口配置：'+ '、'.join(missing),flush=True)
        print('请双击“配置接口.cmd”填写并保存，然后重新启动。',flush=True);return 1
    try:
        import uvicorn,mcp,langgraph,httpx,sqlite3,hashlib as crypto
        crypto.scrypt(b'check',salt=b'portable',n=2**14,r=8,p=1,dklen=16)
    except (ImportError,OSError,ValueError) as e:
        print('运行环境检查未通过：'+type(e).__name__+'。请重新完整解压体验包。',flush=True);return 1
    if args.check:print('运行环境与接口配置检查通过。',flush=True);return 0
    ports=[args.port] if args.port else list(range(8767,8777))
    runtime=ROOT/'data/runtime';runtime.mkdir(parents=True,exist_ok=True)
    import msvcrt
    lock=(runtime/'launcher.lock').open('a+b');lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('这份体验包已经在启动或运行，无需重复启动。',flush=True)
        for _ in range(30):
            port,reuse=find_port(ports)
            if reuse:
                if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{port}/')
                lock.close();return 0
            time.sleep(.5)
        print('请查看原启动窗口；已有服务或数据未被停止。',flush=True);lock.close();return 1
    process=None
    try:
        port,reuse=find_port(ports)
        if port is None:print('可用端口均被占用，请关闭对应服务或用 --port 指定其他端口。',flush=True);return 1
        url=f'http://127.0.0.1:{port}/'
        if reuse:
            print('体验版已经在运行：'+url,flush=True)
            if not args.no_browser:webbrowser.open(url)
            return 0
        if port!=8767:print('默认端口不可用，体验版使用独立端口 '+str(port)+'。',flush=True)
        env={**os.environ,'APP_PUBLIC_ORIGIN':url.rstrip('/'),'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        print('正在启动识途体验版，请稍候……',flush=True)
        with (runtime/'server.log').open('ab',buffering=0) as log:
            process=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            for _ in range(120):
                if process.poll() is not None:print('服务启动失败，请查看 data/runtime/server.log。',flush=True);return 1
                if healthy(port):break
                time.sleep(.5)
            else:print('启动等待超时，请查看 data/runtime/server.log。',flush=True);return 1
            print('已启动：'+url,flush=True)
            if args.check_service:
                # Isolated packaging smoke check: no supplier queries or account creation.
                with sqlite3.connect(runtime/'travel.db') as db:
                    counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('users','workspaces','jobs','feedback','cache')}
                if any(counts.values()):print('体验版初始记录非空，检查失败。',flush=True);return 1
                print('服务、MCP与空白数据库检查通过。',flush=True);return 0
            print('首次使用请注册新账户。数据仅保存在这份体验包中。',flush=True)
            print('保持此窗口开启；按 Ctrl+C 停止。',flush=True)
            if not args.no_browser:webbrowser.open(url)
            return process.wait()
    except KeyboardInterrupt:
        print('\n正在停止体验版。',flush=True);return 0
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

if __name__=='__main__':sys.exit(main())
