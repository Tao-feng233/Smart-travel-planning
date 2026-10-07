"""Explicit, repeatable knowledge initialization; runtime never downloads models."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.embeddings import get_encoder
from app.knowledge import load_corpus
from app.vector_index import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-model', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        result = build(load_corpus(), get_encoder(args.download_model), args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'reason': '初始化失败，请检查资料、模型缓存及Qdrant配置'}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
