"""Extract and boot the portable package without the development Python on PATH."""
import hashlib,json,os,shutil,subprocess,uuid,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    build=json.loads((ROOT/'data/runtime/package-build/latest-build.json').read_text(encoding='utf-8'))
    archive=Path(build['archive']);stage=Path(build['stage'])
    # Refresh the launcher before sealing; neither the staged nor shipped data directory is used for QA.
    shutil.copy2(ROOT/'scripts/launch.py',stage/'scripts/launch.py')
    manifest=json.loads((stage/'package-manifest.json').read_text(encoding='utf-8'))
    manifest['files_sha256']['scripts/launch.py']=hashlib.sha256((stage/'scripts/launch.py').read_bytes()).hexdigest()
    (stage/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in stage.rglob('*'):
            if p.is_file():z.write(p,stage.name+'/'+p.relative_to(stage).as_posix())
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        assert not any('/data/runtime/' in n or n.endswith(('.db','.db-wal','.db-shm')) for n in names)
        assert not any('.展示检查' in n or '/backups/' in n for n in names)
        test=ROOT/'data/runtime/package-tests'/('extract-'+uuid.uuid4().hex[:8]);test.mkdir(parents=True)
        z.extractall(test)
    package=test/stage.name;python=package/'.runtime/python.exe'
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','CONDA_PREFIX','CONDA_DEFAULT_ENV','APP_PUBLIC_ORIGIN')}
    system=env.get('SystemRoot',r'C:\Windows');env.update(PATH=system+'\\System32;'+system,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    checks=[]
    for options in (['--check'],['--check-service','--no-browser']):
        r=subprocess.run([str(python),'-X','utf8',str(package/'scripts/launch.py'),*options],cwd=package,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        print(r.stdout.rstrip())
        if r.returncode:raise RuntimeError('Portable check failed: '+str(r.returncode)+' '+r.stderr[:1000])
        checks.append(options[0])
    (archive.with_suffix('.sha256')).write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='utf-8')
    result={'passed':True,'archive':str(archive),'size_mb':round(archive.stat().st_size/1048576,1),'no_original_history':True,'config_included':manifest['config_included'],'development_python_removed_from_path':True,'portable_check':checks,'test_extraction':str(package)}
    (ROOT/'data/runtime/package-build/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Portable package verified; original records excluded; startup and MCP passed.')
    return result

if __name__=='__main__':main()
