"""Allowlisted portable release: runtime + public knowledge, never local user data."""
import argparse,hashlib,importlib.metadata,json,shutil,sys,sysconfig,uuid,zipfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME_URL='https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip'

def copy_files(source,target):
    for p in source.rglob('*'):
        rel=p.relative_to(source)
        if not p.is_file() or '__pycache__' in rel.parts or p.suffix in ('.pyc','.pyo') or p.name=='direct_url.json':continue
        out=target/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)

def build(include_env=False):
    runtime_zip=ROOT/'data/runtime/package-build/python-3.13.9-embed-amd64.zip'
    if hashlib.md5(runtime_zip.read_bytes()).hexdigest()!='f41c7640d30159cbbc708d9386d01d94':raise ValueError('Official runtime integrity check failed')
    tag='20261007-v10-'+uuid.uuid4().hex[:6]
    release_name='识途体验版-Windows64-'+tag
    stage=ROOT/'data/runtime/package-build'/release_name
    stage.mkdir(parents=True,exist_ok=False)
    for folder in ('app','frontend','data/knowledge','data/catalog'):copy_files(ROOT/folder,stage/folder)
    (stage/'scripts').mkdir();shutil.copy2(ROOT/'scripts/launch.py',stage/'scripts/launch.py')
    for name in ('.env.example','requirements-lock.txt'):shutil.copy2(ROOT/name,stage/name)
    cookie='shitu_trial_'+uuid.uuid4().hex[:12]
    if include_env:
        (stage/'.env').write_text((ROOT/'.env').read_text(encoding='utf-8-sig').rstrip()+'\n\n# 体验版独立登录 Cookie\nAPP_COOKIE_NAME='+cookie+'\n',encoding='utf-8')
    runtime=stage/'.runtime';runtime.mkdir()
    with zipfile.ZipFile(runtime_zip) as z:z.extractall(runtime)
    (runtime/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n..\nimport site\n',encoding='utf-8')
    copy_files(Path(sysconfig.get_paths()['purelib']),runtime/'Lib/site-packages')
    cmd='''@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
if not exist ".runtime\\python.exe" (
  echo 运行环境不完整。请先把整个 ZIP 解压到一个文件夹，不要在压缩包中启动。
  pause
  exit /b 1
)
".runtime\\python.exe" -X utf8 "scripts\\launch.py"
set "taskExitCode=%errorlevel%"
if not "%taskExitCode%"=="0" pause
exit /b %taskExitCode%
'''
    (stage/'启动识途.cmd').write_text(cmd,encoding='utf-8',newline='\r\n')
    (stage/'配置接口.cmd').write_text('@echo off\nchcp 65001 >nul\ncd /d "%~dp0"\nif not exist ".env" copy /y ".env.example" ".env" >nul\nnotepad.exe ".env"\n',encoding='utf-8',newline='\r\n')
    readme='''识途 · Windows 64位体验版

使用方法
1. 完整解压 ZIP 到一个可写文件夹，不要直接在压缩包内运行。
2. 双击“启动识途.cmd”。运行环境已经随包附带，不用安装 Python，也不需要下载依赖。
3. 启动成功会自动打开浏览器。首次使用请注册新账户，保存恢复码。
4. 请保持启动窗口开启。按 Ctrl+C 或关闭窗口可结束本次服务。

接口配置
'''+('本包已按所有者要求带入当前 .env。请仅转交给可信的体验者，调用使用所有者的接口额度。\n' if include_env else '本包不带接口密钥。请双击“配置接口.cmd”填写配置后再启动。\n')+'''
记录与隔离
本包没有原作者的账户、密码哈希、旅行、对话、计划、反馈、备份、查询缓存和调试截图。
首次运行后，新记录保存在本文件夹的 data/runtime；不会读取原项目的数据库。
默认端口为8767；被占用时会自动选择8768–8776中的空闲端口，不会停止其他程序。
重复双击启动不会重复启动同一份体验包。登录Cookie也与原项目分开。
新的旅行会持续保存在这份解压目录中；下次启动可以继续。此功能不会自动清除体验者的记录。

体验流程
描述目的地、日期、人数、预算和偏好 → 景点选择 → 住宿与房型 → 往返交通 → 可选餐饮 → 旅行计划书。
去程和返程日期可分别修改；默认游玩结束次日返程。餐饮可按日期与餐次选择，也可自行安排。
页面使用一排导航，交通确认后进入餐饮，可选择餐厅或明确自行安排；资料在右侧标题旁查看。对话中的地点、酒店和房型可点击定位，卡片点击打开详情、图片和周边地图。长行程支持1至60天，计划按阶段生成；同城出游无需外地往返车票。
地图支持全国范围拖动、鼠标位置滚轮缩放、双击位置放大及加减按钮；操作立即响应，停止后补充清晰底图。显示全部为100%并恢复中心；重置中心点只恢复位置、保留比例；全国按钮直接切到全国。按日期查看每日线路：有道路坐标的段落绘制高德实际通行路线；未取得道路数据时显示顺序示意，出行请使用实时导航。
餐厅和景点详情打开时会补查一次地图资料，支持手动更新；展示特色标签、营业资料、电话、人均、照片与商圈，字段缺失保留待核实。酒店详情保留来源提供的全部房型（技术保护最多100种）、面积、楼层、房间图片、退改和查询时可售状态。
门票按景点的指定游玩日、已生成日程或建议日查询，也可单独改日期；含门票产品与文创/餐食/附加体验分类显示，名称重试不扩大子景点入园范围。区间最低价不当作当天准确报价，预约名额未提供即标未知。
候选有来源；选定不代表预订。票价、余票和天气会变化，尚未核实的信息在计划中说明。

常见问题
网页不能打开：查看启动窗口显示的实际网址；端口改变后不要仍访问旧网址。
首次启动异常：确认完整解压且所在目录可写；运行“配置接口.cmd”检查是否填齐。
查询失败：检查网络、接口配置和额度；不要反复启动或反复发起同一查询。
服务启动失败：错误信息在 data/runtime/server.log；反馈问题时请勿发送 .env 或密钥。
本包面向 Windows 10/11、x64 电脑；不适用于macOS、Linux或Windows ARM原生环境。
'''
    (stage/'先看这里.txt').write_text(readme,encoding='utf-8-sig')
    packages=sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())
    notice='运行环境：Python 3.13.9 官方Windows嵌入版（x64）。\n来源：'+RUNTIME_URL+'\nPSF许可证随 .runtime/LICENSE.txt 分发（具体文件名见该目录）。\n第三方组件沿用对应安装包授权；许可证保留在 .runtime/Lib/site-packages 各包或 dist-info/licenses 中。\n\n'+ '\n'.join(n+'=='+v for n,v in packages)
    (stage/'第三方组件说明.txt').write_text(notice,encoding='utf-8-sig')
    entries={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
    forbidden=[name for name in entries if name.startswith('data/runtime/') or any(x in name for x in ('.展示检查','travel.db','backups/','.venv/','__pycache__'))]
    if forbidden:raise ValueError('Private runtime files unexpectedly entered release')
    manifest={'version':'v10','client_release_date':'2026-10-07','target':'Windows x64','python':'3.13.9','config_included':include_env,'original_history_included':False,'runtime_download_sha256':hashlib.sha256(runtime_zip.read_bytes()).hexdigest(),'files_sha256':entries}
    (stage/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    dist=ROOT/'dist';dist.mkdir(exist_ok=True);archive=dist/(release_name+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in stage.rglob('*'):
            if p.is_file():z.write(p,release_name+'/'+p.relative_to(stage).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert not any('/data/runtime/' in n or n.endswith(('.db','.db-wal','.db-shm')) for n in z.namelist())
        assert (release_name+'/.env' in z.namelist())==include_env
    (dist/(release_name+'.sha256')).write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='utf-8')
    result={'archive':str(archive),'stage':str(stage),'size_mb':round(archive.stat().st_size/1048576,1),'file_count':len(entries),'private_records':0,'config_included':include_env}
    (ROOT/'data/runtime/package-build/latest-build.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--include-env',action='store_true',help='Only use when the owner explicitly authorizes sharing their API configuration')
    build(p.parse_args().include_env)
