from pathlib import Path
import os
import hashlib
from dataclasses import dataclass,field
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
VALUES = dotenv_values(ROOT / '.env', encoding='utf-8-sig')

def setting(name: str, default: str = '') -> str:
    if name=='APP_PUBLIC_ORIGIN' and os.environ.get(name):return os.environ[name].strip()
    return str(VALUES.get(name) or default).strip()

@dataclass(frozen=True)
class TuniuCredential:
    slot:str
    key:str=field(repr=False)
    account:str=''


def tuniu_credentials():
    """Numbered keys take precedence; optional account labels group shared quotas."""
    entries=[];seen=set()
    for i in range(1,5):
        key=setting(f'TUNIU_API_KEY_{i}')
        if not key or key in seen:continue
        seen.add(key)
        label=setting(f'TUNIU_API_ACCOUNT_{i}')
        identity='account:'+label if label else 'key:'+key
        entries.append(TuniuCredential(f'TUNIU_API_KEY_{i}',key,'tuniu:'+hashlib.sha256(identity.encode()).hexdigest()[:24]))
    if not entries and setting('TUNIU_API_KEY'):
        entries=[TuniuCredential('TUNIU_API_KEY',setting('TUNIU_API_KEY'),'tuniu')]
    return entries


def configured() -> dict:
    result={k: bool(setting(k)) for k in ('AMAP_API_KEY','QWEATHER_API_KEY','QWEATHER_API_HOST','LLM_API_KEY')}
    result['TUNIU_API_KEY']=bool(tuniu_credentials())
    return result
