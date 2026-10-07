"""Refresh reviewed official sources; failures keep previous valid documents."""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.storage import now, RUNTIME
from app.knowledge_collection import collect, publish
from app.public_fetch import PublicFetcher


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',default='data/knowledge-sources.json')
    parser.add_argument('--output',default='data/knowledge/official-pages.json')
    args=parser.parse_args()
    registry = json.loads((ROOT / args.registry).read_text(encoding='utf-8'))
    destination = ROOT / args.output
    previous = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else []
    with PublicFetcher() as fetch:
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
    (RUNTIME / (destination.stem+'-collection-report.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (RUNTIME / 'knowledge-collection-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(row['status'] == 'failed' for row in report) else 0


if __name__ == '__main__':
    raise SystemExit(main())
