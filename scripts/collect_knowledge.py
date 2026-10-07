"""Refresh reviewed official sources; failures keep previous valid documents."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import ROOT
from app.storage import now, RUNTIME
from app.knowledge_collection import collect, publish


def main():
    registry = json.loads((ROOT / 'data/knowledge-sources.json').read_text(encoding='utf-8'))
    destination = ROOT / 'data/knowledge/official-pages.json'
    previous = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else []
    with httpx.Client(timeout=20, follow_redirects=True, headers={'User-Agent': 'ShituKnowledgeCollector/1.0'}) as client:
        def fetch(source):
            response = client.get(source['url'])
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type', '').lower():
                raise ValueError('Expected HTML')
            return response.content, str(response.url)
        records, report = collect(registry, previous, fetch, now())
    if records:
        if destination.exists():
            from app.knowledge import digest
            archive = RUNTIME / 'knowledge-history'
            archive.mkdir(parents=True, exist_ok=True)
            (archive / (digest(previous) + '.json')).write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
        publish(destination, records)
    result = {'sources': report, 'documents': len(records)}
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / 'knowledge-collection-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(row['status'] == 'failed' for row in report) else 0


if __name__ == '__main__':
    raise SystemExit(main())
