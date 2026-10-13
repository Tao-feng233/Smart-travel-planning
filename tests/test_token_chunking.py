"""Real BGE token budgets, intact source text, and versioned corpus splitting."""

import json

from app.knowledge import corpus


def counter():
    from app.knowledge.tokenization import get_counter

    return get_counter()


def record(text, **extra):
    return {
        "id": "guide",
        "city": "青岛",
        "title": "景区预约与开放说明",
        "url": "https://example.test/guide",
        "text": text,
        **extra,
    }


def load(tmp_path, text, **extra):
    (tmp_path / "guides.json").write_text(
        json.dumps([record(text, **extra)], ensure_ascii=False), encoding="utf-8"
    )
    return corpus.load_corpus(tmp_path)


def test_counter_does_not_truncate_at_embedding_limit():
    c = counter()
    assert c.count("预约" * 900) > 512
    assert c.count("预约", special_tokens=True) == c.count("预约") + 2


def test_token_split_preserves_long_original_sentences_and_unicode():
    c = counter()
    text = ("青岛 seaside WALK 预约❄️🙂、亲子游123 " * 90).strip()
    chunks = corpus.split_text(text, max_tokens=60, overlap=0)
    assert len(chunks) > 1
    assert all(c.count(chunk) <= 60 for chunk in chunks)
    # Cutting must not decode normalized token IDs back into different source text.
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")
    assert all(chunk in text for chunk in chunks)


def test_sentence_boundaries_and_token_overlap():
    c = counter()
    text = "请提前预约。请携带证件。周一闭馆。节假日除外。请有序排队。"
    chunks = corpus.split_text(text, max_tokens=18, overlap=4)
    assert len(chunks) > 1
    assert all(c.count(chunk) <= 18 for chunk in chunks)
    assert all(chunk.endswith("。") for chunk in chunks)
    assert any(a[-4:] == b[:4] for a, b in zip(chunks, chunks[1:]))


def test_corpus_parent_and_complete_index_input_have_token_budgets(tmp_path):
    c = counter()
    loaded = load(tmp_path, "预约须知：" + "请提前预约并携带证件。" * 240)
    assert len(loaded["parents"]) > 1
    assert all(c.count(p["text"]) <= 1400 for p in loaded["parents"].values())
    assert all(
        c.count(child["index_text"], special_tokens=True) <= 360
        for child in loaded["children"]
    )
    assert all(
        child["text"] in loaded["parents"][child["parent_id"]]["text"]
        for child in loaded["children"]
    )
    assert loaded["split"]["unit"] == "tokens"


def test_long_title_is_included_in_child_budget(tmp_path):
    c = counter()
    loaded = load(tmp_path, "请提前预约。" * 120, title="预约须知" * 35)
    assert len(loaded["children"]) > 1
    assert all(
        c.count(child["index_text"], special_tokens=True) <= 360
        for child in loaded["children"]
    )


def test_ascii_text_can_use_more_characters_without_more_tokens():
    text = "Travel planning includes sightseeing and lunch. " * 20
    chunks = corpus.split_text(text, max_tokens=80, overlap=0)
    assert any(len(chunk) > 80 for chunk in chunks)
    assert all(counter().count(chunk) <= 80 for chunk in chunks)
