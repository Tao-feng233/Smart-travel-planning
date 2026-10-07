"""Local administrator command: explicitly associate old unowned trips with an existing account."""
import argparse,json,sqlite3,sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import storage

def main():
    parser=argparse.ArgumentParser(description='将升级前未归属账户的本机旅行迁移给指定用户；只在本机命令行运行。')
    parser.add_argument('--username',required=True);args=parser.parse_args()
    with storage.connect() as c:
        user=c.execute('SELECT id FROM users WHERE username=?',(args.username.lower().strip(),)).fetchone()
        if not user:raise SystemExit('请先在网页注册该用户名，再执行迁移。')
        rows=c.execute('SELECT id,payload FROM workspaces WHERE owner_id IS NULL').fetchall()
    selected=[r for r in rows if json.loads(r[1]).get('messages') or json.loads(r[1]).get('plan')]
    if not selected:print('没有需要迁移的旧旅行。');return
    backup=storage.RUNTIME/'backups'/('before-legacy-import-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db');backup.parent.mkdir(exist_ok=True)
    with storage.connect() as a,sqlite3.connect(backup) as b:a.backup(b)
    with storage.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for wid,payload in selected:
            w=json.loads(payload);w['owner_id']=user[0]
            c.execute('UPDATE workspaces SET owner_id=?,payload=? WHERE id=? AND owner_id IS NULL',(user[0],json.dumps(w,ensure_ascii=False),wid))
    print(f'已迁移 {len(selected)} 次旅行。请在网页“我的旅行”中查看。迁移前数据库已备份。')

if __name__=='__main__':main()
