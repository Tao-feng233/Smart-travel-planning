"""改动1：餐次时刻跟随前后活动，而不是固定在默认时刻。

背景（用户反馈）：西湖 09:00–13:00 结束，午餐默认 12:00 开始，
系统不会把午餐挪到 13:00，只会把景区切成碎片或让用户"午餐自行安排"。
工具其实早就有（meal_start 的 as_late 能给返程日"尽量晚开饭"），只是没用在普通日。

这里新增 resolve_meals：在景点排布确定之后，把每一餐放到
"不与任何景点重叠、且落在自己窗口内"的位置——
优先靠近默认时刻，被长时景点跨过时顺延到景点结束。
"""
from . import pacing as _pacing


def _clock(minutes):
    minutes = max(0, min(24 * 60, int(minutes)))
    return '%02d:%02d' % (minutes // 60, minutes % 60)


def resolve_meals(w, dt, visits, preferred):
    """把每餐安排在不与景点重叠、且落在窗口内的时刻。

    visits：[(start, finish)]，已排定的景点与午休区间（分钟）。
    preferred：{period: 默认开饭时刻}（已含返程日"尽量晚"的口径）。
    返回 {period: 开饭时刻或 None}。
    """
    gaps = sorted((int(a), int(b)) for a, b in visits if b > a)
    from . import schedule as _schedule   # 延迟导入：schedule 会引用本模块
    out = {}
    for period, want in preferred.items():
        begin, end = _schedule.meal_window(w, dt, period)
        duration = _pacing.meal_duration(w, dt, period)
        if want is None or begin + duration > end:
            out[period] = None
            continue
        latest = end - duration

        def hits(start):
            return any(start < b and a < start + duration for a, b in gaps)

        # 1) 默认时刻可用
        if not hits(want):
            out[period] = want
            continue
        # 2) 紧接在相关活动结束后开饭（优先"跨过 want 的那段"，否则其后最近的一段）
        spanning = [b for a, b in gaps if a < want < b]
        following = [a for a, b in gaps if a >= want]
        candidates = ([max(spanning)] if spanning else []) + (sorted(following) if following else [])
        picked = None
        for candidate in candidates:
            if begin <= candidate <= latest and not hits(candidate):
                picked = candidate
                break
        if picked is not None:
            out[period] = picked
            continue
        # 3) 活动开始前
        before = [a - duration for a, b in gaps if a < want < b]
        for candidate in before:
            if begin <= candidate <= latest and not hits(candidate):
                picked = candidate
                break
        if picked is not None:
            out[period] = picked
            continue
        # 4) 窗口内最近空档
        found = None
        probe = begin
        while probe <= latest:
            if not hits(probe):
                found = probe
                break
            probe += 5
        out[period] = found
    return out
