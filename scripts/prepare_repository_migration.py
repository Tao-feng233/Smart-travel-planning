"""Build a public-source snapshot without copying credentials or local records."""
from pathlib import Path
import hashlib,json,re,shutil,zipfile
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/'data/runtime/repository-migration'
STAGE=MIGRATION/'current-project'
BACKUP=ROOT/'repository-backups/Smart-travel-planning-20261007-dc53d5b'
OLD_SHA='dc53d5b3c914bf4c446809b01d508efbcbbbbc0d'

def scan(files):
    configured=dotenv_values(ROOT/'.env',encoding='utf-8-sig')
    secrets=[v for k,v in configured.items() if v and len(v)>=12 and any(t in k.upper() for t in ('KEY','TOKEN','SECRET','PASSWORD'))]
    issues=[]
    patterns=[re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{30,}\b'),re.compile(rb'\bsk-[A-Za-z0-9_-]{24,}\b'),re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
    for path in files:
        data=path.read_bytes()
        if any(v.encode() in data for v in secrets):issues.append({'path':str(path.relative_to(STAGE)),'type':'configured_secret'})
        for pattern in patterns:
            if pattern.search(data):issues.append({'path':str(path.relative_to(STAGE)),'type':'credential_pattern'})
    if issues:
        print(json.dumps({'secret_scan_passed':False,'issues':issues},ensure_ascii=True));raise SystemExit(1)

def copy_file(source,dest):
    if source.is_symlink():raise ValueError('Do not copy symlinks into release')
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)

def main():
    if STAGE.exists():raise ValueError('Staging directory already exists; preserve existing staging')
    STAGE.mkdir(parents=True)
    for folder in ('app','frontend','tests','data/knowledge','data/catalog'):
        for f in (ROOT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.pyo'):copy_file(f,STAGE/f.relative_to(ROOT))
    scripts=('start.py','launch.py','collect_knowledge.py','import_legacy.py','probe.py','build_trial.py','verify_trial_package.py',
             'browser_accounts.cjs','browser_map_v9.cjs','browser_enrichment_v10.cjs','browser_live_map_v9.cjs','browser_live_v8.cjs')
    for name in scripts:copy_file(ROOT/'scripts'/name,STAGE/'scripts'/name)
    for name in ('.env.example','.gitignore','README.md','CONTEXT.md','requirements.txt','requirements-lock.txt','启动.cmd','启动.ps1',
                 'docs/design/产品功能结构.md','docs/design/地图与客流设计.md','docs/reference/官方接口核对.md','docs/status/开发状态.md','docs/design/旅游规划项目方案.md','docs/reference/途牛.md','docs/design/项目构思与原型评审.md'):
        copy_file(ROOT/name,STAGE/name)
    for f in (ROOT/'output').iterdir():
        if f.is_file() and ('面试技术资料' in f.name or '业务逻辑图' in f.name or '技术架构图' in f.name or 'Agent执行流程图' in f.name):
            copy_file(f,STAGE/'docs/project-report'/f.name)
    copy_file(ROOT/'output/pdf/识途项目面试技术资料.pdf',STAGE/'docs/project-report/识途项目面试技术资料.pdf')
    for f in (ROOT/'docs/legacy').rglob('*'):
        if f.is_file():copy_file(f,STAGE/f.relative_to(ROOT))
    files=sorted(x for x in STAGE.rglob('*') if x.is_file())
    for f in files:
        rel=f.relative_to(STAGE)
        if f.name.startswith('.env') and rel.as_posix()!='.env.example':raise ValueError('Unexpected env file')
        if any(x in rel.parts for x in ('runtime','dist','.venv','repository-backups','.git','.idea','.展示检查')):raise ValueError('Local data in stage')
    scan(files)
    manifest={f.relative_to(STAGE).as_posix():{'size':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),
        'git_blob_sha':hashlib.sha1(b'blob '+str(f.stat().st_size).encode()+b'\0'+f.read_bytes()).hexdigest()} for f in files}
    info={'repository':'Tao-feng233/Smart-travel-planning','previous_head':OLD_SHA,'backup_directory':str(BACKUP),
          'stage_directory':str(STAGE),'file_count':len(files),'total_bytes':sum(v['size'] for v in manifest.values()),
          'secret_scan_passed':True,'env_included':False,'original_records_included':False,'files':manifest}
    (MIGRATION/'manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(MIGRATION/'current-public-source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in files:z.write(f,f.relative_to(STAGE).as_posix())
    print(json.dumps({k:v for k,v in info.items() if k!='files'},ensure_ascii=True))

if __name__=='__main__':main()
