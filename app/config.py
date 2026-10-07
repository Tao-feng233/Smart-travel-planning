from pathlib import Path
import os
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
VALUES = dotenv_values(ROOT / '.env', encoding='utf-8-sig')

def setting(name: str, default: str = '') -> str:
    if name=='APP_PUBLIC_ORIGIN' and os.environ.get(name):return os.environ[name].strip()
    return str(VALUES.get(name) or default).strip()

def configured() -> dict:
    return {k: bool(setting(k)) for k in ('AMAP_API_KEY', 'QWEATHER_API_KEY', 'QWEATHER_API_HOST', 'LLM_API_KEY', 'TUNIU_API_KEY')}
