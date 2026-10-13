"""BGE token counting and source-preserving, sentence-first text splitting.

The small tokenizer is bundled independently of model weights so lexical
retrieval and collection still work before the embedding model is initialized.
"""

from functools import lru_cache
import hashlib
import re

from tokenizers import Tokenizer

from app.core.config import ROOT

TOKENIZER_MODEL = "BAAI/bge-small-zh-v1.5"
TOKENIZER_FILE = ROOT / "data/tokenizers/bge-small-zh-v1.5/tokenizer.json"
PARENT_TOKENS = 1400
CHILD_TOKENS = 360
OVERLAP_TOKENS = 50


class TokenCounter:
    def __init__(self, path=TOKENIZER_FILE):
        self.tokenizer = Tokenizer.from_file(str(path))
        # FastEmbed's saved tokenizer truncates at 512 and pads short inputs.
        # Counting must see the entire input, without mutating its inference copy.
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()

    def count(self, text, *, special_tokens=False):
        return len(self.tokenizer.encode(text, add_special_tokens=special_tokens).ids)

    def tail(self, text, limit):
        if not limit:
            return ""
        offsets = self.tokenizer.encode(text, add_special_tokens=False).offsets
        # Re-encoding a suffix can change WordPiece boundaries. Verify its length.
        for start, _ in offsets[-limit:]:
            suffix = text[start:]
            if self.count(suffix) <= limit:
                return suffix
        return ""


@lru_cache(maxsize=1)
def get_counter():
    return TokenCounter()


def split_contract():
    return {
        "unit": "tokens",
        "tokenizer_model": TOKENIZER_MODEL,
        "tokenizer_fingerprint": get_counter().fingerprint,
        "parent": PARENT_TOKENS,
        "child": CHILD_TOKENS,
        "overlap": OVERLAP_TOKENS,
        "child_includes_prefix_and_special_tokens": True,
    }


def split_text(
    text,
    max_tokens=CHILD_TOKENS,
    overlap=OVERLAP_TOKENS,
    *,
    prefix="",
    special_tokens=False,
):
    """Keep original characters; token offsets never decode or normalize text."""
    if not 0 <= overlap < max_tokens:
        raise ValueError("重叠 Token 数必须小于片段预算")
    counter = get_counter()

    def fits(body):
        return counter.count(prefix + body, special_tokens=special_tokens) <= max_tokens

    if not fits(""):
        raise ValueError("城市与标题前缀已经超过子块 Token 预算")

    def pieces(sentence):
        while sentence:
            if fits(sentence):
                yield sentence
                return
            # Only oversized sentences need hard cuts. Preserve the original
            # Unicode characters instead of decoding normalized tokenizer IDs.
            low, high = 0, len(sentence)
            while low < high:
                middle = (low + high + 1) // 2
                if fits(sentence[:middle]):
                    low = middle
                else:
                    high = middle - 1
            if not low:
                raise ValueError("子块 Token 预算不足以容纳正文")
            yield sentence[:low]
            sentence = sentence[low:]

    chunks = []
    current = ""
    for sentence in re.findall(r"[^。！？；\n]+[。！？；\n]?|[。！？；\n]", text):
        for piece in pieces(sentence):
            if current and not fits(current + piece):
                chunks.append(current)
                tail = counter.tail(current, overlap)
                current = tail + piece if fits(tail + piece) else piece
            else:
                current += piece
    if current:
        chunks.append(current)
    return chunks
