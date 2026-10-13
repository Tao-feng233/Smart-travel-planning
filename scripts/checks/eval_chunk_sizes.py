"""Chunk-size comparison for the parent/child retrieval pipeline.

Parent size stays at the production 1400 BGE tokens; only the child token budget varies.
For each split size we measure, against a hand-labelled needle set:
  1. how many children exceed the encoder's 512-token limit (silent truncation),
  2. whether the needle sentence survives inside the encoder window,
  3. whether the needle is retrieved (dense / BM25 / fused) and reaches the
     generator under the production context budget.
Writes a JSON report to --out. Read-only against app/.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.knowledge.corpus import load_corpus, split_text, bm25, fuse, applicable
from app.knowledge.embeddings import get_encoder
from app.core.data_settings import model_name
from app.knowledge.tokenization import get_counter

SIZES = [128, 256, 360, 500, 512, 700, 1400]
OVERLAP = 50
DENSE_MIN_SCORE = 0.58
CONTEXT_CHARS = 6000
CONTEXT_LIMIT = 5
ENCODER_LIMIT = 512  # Complete encoded input, including [CLS]/[SEP].


def needles():
    """(question, city, evidence sentence that answers it)."""
    return [
        ("坐索道上泰山多少钱，老年人有没有优惠", "泰安", "单程100元"),
        ("泰山有什么特色美食值得吃", "泰安", "赤鳞鱼"),
        ("从天烛峰那条线路登山，离泰山火车站有多远", "泰安", "约20公里"),
        ("杜甫草堂的年票怎么收费", "成都", "年票（卡）100元"),
        ("老年人去杜甫草堂要买票吗", "成都", "年满60周岁"),
        (
            "冬天去熊猫基地，上午几点能入园",
            "成都",
            "11月至次年2月——上午票入园时间：8:00-12:00",
        ),
        ("熊猫基地能不能带无人机进去", "成都", "无人机"),
        ("曹州牡丹园改造工程总共投了多少钱", "菏泽", "6000万元"),
        ("牡丹花会的开幕式在哪里办的", "菏泽", "牡丹广场"),
        ("国花馆里都有什么展览内容", "菏泽", "一楼分历史厅和荣誉厅"),
        ("青岛的凤凰岛度假区怎么样", "青岛", "凤凰岛"),
        ("沂蒙云瀑洞天这个景区有什么看点", "临沂", "云瀑洞天"),
        ("东阿阿胶那边有什么可以体验的", "聊城", "阿胶"),
    ]


def load_tokenizer():
    return get_counter().tokenizer


def build_children(parents, size, tokenizer):
    """Split every production parent into children of the given size."""
    children = []
    for pid, parent in parents.items():
        overlap = OVERLAP if size < 1400 else 0
        prefix = parent["city"] + " " + parent["title"] + " "
        for body in split_text(
            parent["text"], size, overlap, prefix=prefix, special_tokens=True
        ):
            children.append(
                dict(
                    id=f"{pid}@c{len(children)}",
                    parent_id=pid,
                    body=body,
                    index_text=prefix + body,
                    tokens=len(tokenizer.encode(prefix + body).ids),
                    prefix_tokens=len(tokenizer.encode(prefix).ids),
                )
            )
    return children


def evidence_visibility(child, evidence, tokenizer):
    """Whether the evidence sentence sits inside the encoder window of this child."""
    at = child["body"].find(evidence)
    if at < 0:
        return None
    upto = child["index_text"].find(evidence) + len(evidence)
    tokens_upto = len(tokenizer.encode(child["index_text"][:upto]).ids)
    return {
        "char_pos": at,
        "body_len": len(child["body"]),
        "tokens_upto_evidence": tokens_upto,
        "truncated": tokens_upto > ENCODER_LIMIT,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="chunk-eval.json")
    args = parser.parse_args()

    corpus = load_corpus()
    parents = corpus["parents"]
    tokenizer = load_tokenizer()
    encoder = get_encoder(allow_download=False)
    cases = needles()

    from qdrant_client import QdrantClient, models

    report = {
        "model": model_name(),
        "parent_size": 1400,
        "size_unit": "BGE tokens",
        "child_includes_prefix_and_special_tokens": True,
        "overlap": OVERLAP,
        "encoder_token_limit": 512,
        "context_chars": CONTEXT_CHARS,
        "context_limit": CONTEXT_LIMIT,
        "cases": len(cases),
        "sizes": {},
    }

    for size in SIZES:
        started = time.time()
        children = build_children(parents, size, tokenizer)
        by_id = {c["id"]: c for c in children}
        allowed_parents = {pid for pid, p in parents.items() if applicable(p)}
        allowed = [c for c in children if c["parent_id"] in allowed_parents]

        over = [c for c in children if c["tokens"] > 512]
        vectors = []
        texts = [c["index_text"] for c in children]
        for at in range(0, len(texts), 32):
            vectors.extend(encoder.documents(texts[at : at + 32]))
        build_seconds = time.time() - started

        client = QdrantClient(":memory:")
        collection = f"eval_{size}"
        client.create_collection(
            collection,
            vectors_config={
                "dense": models.VectorParams(
                    size=len(vectors[0]), distance=models.Distance.COSINE
                )
            },
        )
        client.upsert(
            collection,
            points=[
                models.PointStruct(
                    id=i, vector={"dense": v}, payload={"cid": children[i]["id"]}
                )
                for i, v in enumerate(vectors)
            ],
        )

        rows = []
        for question, city, evidence in cases:
            city_allowed = [
                c
                for c in allowed
                if parents[c["parent_id"]]["city"] == city_key_of(parents, city)
            ]
            if not city_allowed:
                city_allowed = allowed
            city_ids = {c["id"] for c in city_allowed}

            # --- evidence bookkeeping
            holders = [c for c in children if evidence in c["body"]]
            visible = [
                c
                for c in holders
                if not evidence_visibility(c, evidence, tokenizer)["truncated"]
            ]
            best_vis = min(
                (
                    evidence_visibility(c, evidence, tokenizer)["tokens_upto_evidence"]
                    for c in visible
                ),
                default=None,
            )

            # --- dense retrieval (production: threshold + parent filter)
            qvec = encoder.query(question)
            raw = client.query_points(
                collection_name=collection,
                query=qvec,
                using="dense",
                limit=60,
                with_payload=True,
            ).points
            dense = [
                (p.payload["cid"], float(p.score))
                for p in raw
                if p.payload["cid"] in city_ids and float(p.score) >= DENSE_MIN_SCORE
            ][:20]

            # --- lexical retrieval
            lexical = bm25(city_allowed, question)[:20]

            # --- RRF fusion, grouped by parent, walked under the context budget
            fused = fuse(lexical, dense)
            grouped = {}
            for cid, score in fused:
                pid = by_id[cid]["parent_id"]
                g = grouped.setdefault(
                    pid, {"score": score, "match": by_id[cid]["body"]}
                )
                g["score"] = max(g["score"], score)
            text_out = ""
            remaining = CONTEXT_CHARS
            for pid, g in sorted(grouped.items(), key=lambda x: -x[1]["score"])[
                :CONTEXT_LIMIT
            ]:
                text = parents[pid]["text"]
                if len(text) > remaining:
                    at = text.find(g["match"])
                    start = max(0, at - 150) if at >= 0 else 0
                    text = text[start : start + remaining]
                text_out += text + "\n"
                remaining -= len(text)

            def rank_in(pairs):
                for index, (cid, _) in enumerate(pairs, 1):
                    if evidence in by_id[cid]["body"]:
                        return index
                return None

            rows.append(
                {
                    "question": question,
                    "evidence": evidence,
                    "holders": len(holders),
                    "visible_holders": len(visible),
                    "truncated_holders": len(holders) - len(visible),
                    "tokens_upto_evidence_best": best_vis,
                    "dense_rank": rank_in(dense),
                    "lexical_rank": rank_in(lexical),
                    "dense_hit": rank_in(dense) is not None,
                    "lexical_hit": rank_in(lexical) is not None,
                    "context_hit": evidence in text_out,
                    "context_chars_used": CONTEXT_CHARS - remaining,
                }
            )
        client.close()

        n = len(rows)
        report["sizes"][str(size)] = {
            "children": len(children),
            "allowed_children": len(children),
            "over_512_tokens": len(over),
            "max_tokens": max(c["tokens"] for c in children),
            "build_seconds": round(build_seconds, 1),
            "dense_hits": sum(r["dense_hit"] for r in rows),
            "lexical_hits": sum(r["lexical_hit"] for r in rows),
            "context_hits": sum(r["context_hit"] for r in rows),
            "cases_truncated_evidence": sum(r["truncated_holders"] > 0 for r in rows),
            "context_chars_median": statistics.median(
                r["context_chars_used"] for r in rows
            ),
            "detail": rows,
        }
        d = report["sizes"][str(size)]
        print(
            f"size={size:5d} children={d['children']:4d} over512={d['over_512_tokens']:3d} "
            f"dense={d['dense_hits']}/{n} lex={d['lexical_hits']}/{n} context={d['context_hits']}/{n} "
            f"trunc_ev={d['cases_truncated_evidence']} build={d['build_seconds']}s",
            flush=True,
        )

    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("written", args.out)


def city_key_of(parents, city):
    from app.knowledge.corpus import city_key

    return city_key(city)


if __name__ == "__main__":
    main()
