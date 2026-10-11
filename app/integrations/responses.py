"""Normalize nested provider response envelopes without inventing fields."""

import json


def unwrap(d):
    for _ in range(4):
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except ValueError:
                break
        elif isinstance(d, dict) and "result" in d:
            d = d["result"]
        else:
            break
    return d
