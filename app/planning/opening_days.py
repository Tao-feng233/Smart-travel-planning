"""开放资料里的"星期闭馆日"解析。

``opening_hours.parse`` 只认时间区间，把"周一闭馆"当成噪音丢掉，于是周一
被当成普通开放日排程。这里补上星期维度，同样遵守``保守优先``：拿不准就返回
None（不拦），绝不会因为读错一行资料而把一个开门的景点判成闭馆--误拦会让
用户白跑一趟，比漏拦更糟。

判定结果是三态，不是布尔：
  True  -- 资料明确说明这天闭馆
  False -- 资料明确说明这天开放
  None  -- 资料没有可用的星期信息，不拦

规则形态（取自高德 opening 原文）：
  "周一闭馆 国家法定节假日除外；11月1日至次年4月30日 周二至周日 09:00-16:30"
  "周一全天关闭（法定节假日除外），周二至周日:9:00-18:00"
  "4月1日-10月31日:09:00-17:30；11月1日-3月31日:周二-周日:09:00-17:30"
  "1月至4月,11月至12月 周一至周日 08:30-17:30 最晚进入16:30"
"""

import re
from datetime import date

WEEKDAY_INDEX = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# 明确写"关闭"的词。注意"停止入馆"不算：那是当天入场截止，不是整天不开放。
_CLOSE_WORDS = r"闭馆|闭园|闭门|关闭|不开放|停业|停开|不营业|休息"
# 但书：资料写明法定节假日例外时，闭馆判定照旧（否则整个能力失效），
# 但必须把但书带进提示，不让用户以为这是确定结论。
_HOLIDAY_EXCEPT = r"法定节假日|节假日除外|国家法定"

_MONTH_WINDOW = re.compile(
    r"(\d{1,2})月(?:\s*(\d{1,2})日)?\s*(?:至|-|—|–|~|到)\s*(次年)?(\d{1,2})月(?:\s*(\d{1,2})日)?"
)
_MONTH_SINGLE = re.compile(r"(\d{1,2})月(?!\s*\d{1,2}日)")
# 第一个星期词必须带"周/星期/礼拜"前缀。不加这个约束，"10月31日-10月"里的
# "日-1" 会被当成星期区间（实测踩到过），凭空造出一条开放日规则。
_WEEK_RANGE = re.compile(
    r"(?:周|星期|礼拜)([一二三四五六日天1-7])\s*(?:至|-|—|–|~|到)\s*"
    r"(?:周|星期|礼拜)?([一二三四五六日天1-7])"
)
_WEEK_ONE = re.compile(r"(?:周|星期|礼拜)([一二三四五六日天1-7])")
_SEGMENT = re.compile(r"[；;。]")


def _as_date(day):
    """接受 date 或 YYYY-MM-DD 字符串；无法识别时返回 None。"""
    if isinstance(day, date):
        return day
    try:
        return date.fromisoformat(str(day)[:10])
    except (ValueError, TypeError):
        return None


def _spans(pattern, text):
    return [m for m in pattern.finditer(text)]


def _window(match):
    """(起始月, 起始日, 结束月, 结束日)；跨年窗口用 次年 或起止倒挂表达。"""
    start_month = int(match.group(1))
    start_day = int(match.group(2) or 1)
    end_month = int(match.group(4))
    end_day = int(match.group(5) or 31)
    return (start_month, start_day, end_month, end_day)


def _in_window(window, month, day):
    if window is None:
        return True
    start, end = (window[0], window[1]), (window[2], window[3])
    now = (month, day)
    if start <= end:
        return start <= now <= end
    # 跨年窗口（11月1日至次年4月30日）
    return now >= start or now <= end


def _tokens(text):
    """按出现顺序产出 (window|month|week_range|week_one, match)。"""
    windows = _spans(_MONTH_WINDOW, text)
    window_spans = [m.span() for m in windows]
    weeks = [
        m
        for m in _spans(_WEEK_RANGE, text)
        if not any(s <= m.start() < e for s, e in window_spans)
    ]
    week_spans = [m.span() for m in weeks]
    tokens = [("window", m) for m in windows] + [("week_range", m) for m in weeks]
    # 单个"12月"只有在没被区间吃掉时才算一条窗口（"5月1日"这类具体日期不算）
    for m in _spans(_MONTH_SINGLE, text):
        if not any(s <= m.start() < e for s, e in window_spans):
            tokens.append(("month", m))
    # "周一"若已属于"周一至周日"，不再单独成词
    for m in _spans(_WEEK_ONE, text):
        if not any(s <= m.start() < e for s, e in window_spans + week_spans):
            tokens.append(("week_one", m))
    return sorted(tokens, key=lambda item: item[1].start())


def _week_days(first, last):
    """把"周二至周日"展开成 {1,2,3,4,5,6}；跨周末尾的区间按环形处理。"""
    start = WEEKDAY_INDEX.get(first)
    end = WEEKDAY_INDEX.get(last)
    if start is None or end is None:
        return set()
    if start <= end:
        return set(range(start, end + 1))
    return set(range(start, 7)) | set(range(0, end + 1))


def _week_spec(kind, match, text, week_count=1):
    """把一个星期词翻成 {open/closed}；无法判定时返回 None。"""
    if kind == "week_range":
        days = _week_days(*match.groups())
    else:
        day = WEEKDAY_INDEX.get(match.group(1))
        days = {day} if day is not None else set()
    if len(days) < (1 if kind == "week_one" else 2):
        return None
    after = text[match.end(): match.end() + 12]
    before = text[max(0, match.start() - 8): match.start()]
    shutting = bool(re.search(_CLOSE_WORDS, after) or re.search(_CLOSE_WORDS, before))
    if kind == "week_one" and not shutting:
        # 整段只有这一个星期词时（"周一 09:00-17:00"），既可能是"仅周一开放"
        # 也可能是资料残缺，保守起见不产出结论。但它若与其它星期词并列出现
        # （"周一,周三至周日 08:30-18:00"），那是开放日枚举，必须算作开放日：
        # 漏掉它就会把明明白白写着开放的周一判成闭馆（实测踩到）。
        if week_count < 2:
            return None
    key = "closed" if shutting else "open"
    return {key: days, "holiday": bool(re.search(_HOLIDAY_EXCEPT, text))}


def rules_of(opening):
    """解析出 [{"months": 窗口|None, "open"/"closed": 星期集合, "holiday": bool}]。

    星期词只绑定它**之前最近的、且尚未绑定过的**月份窗口：这样
    "5月至10月:周二至周日:...；11月至次年4月:09:00-16:30" 里，"周二至周日"
    只在 5-10 月生效，不会把冬季的周一也判成闭馆。
    """
    rules = []
    for segment in _SEGMENT.split(str(opening or "")):
        pending = []
        current = None
        windows_seen = []
        covered = set()
        tokens = _tokens(segment)
        week_count = sum(1 for kind, _ in tokens if kind.startswith("week"))
        for kind, match in tokens:
            if kind == "window":
                pending.append(_window(match))
                windows_seen.append(_window(match))
            elif kind == "month":
                pending.append((int(match.group(1)), 1, int(match.group(1)), 31))
                windows_seen.append(pending[-1])
            else:
                spec = _week_spec(kind, match, segment, week_count)
                if not spec:
                    continue
                # 只绑定最近的那个窗口。绑全部实测会误伤：陕西历史博物馆
                # "4月1日至11月14日 ...,11月15日至3月14日周一 全天关闭"
                # 的"周一全天关闭"只属于 11/15 起那段，套到前一段就会把
                # 11/2（本该开放）判成闭馆。
                # 但该窗口要作为"当前上下文"留给后续星期词：同一段里
                # "周一全天关闭, 周二至周日09:00-17:00" 两句都属于同一个窗口。
                # 月份窗口还没出现 -> 这条星期规则不带月份限定，是全年规则
                # （months=None）。"周一闭馆"写在"11月1日至次年4月30日"左边时
                # 就是这种：闭馆是全年生效的，只有时段才分冬夏令。删掉这个
                # None 分支，7 月的周一就会漏拦（青岛市博物馆 C5 现场）。
                window = pending[-1] if pending else current
                rules.append(dict(spec, months=window))
                if window is not None:
                    covered.add(window)
                if pending:
                    current = pending[-1]
                    pending = []
        # 一段里给了月份窗口和营业时段、却一个星期词都没写，读出来就是
        # "这段时间内没有星期限制"。这不是硬凑结论：它和"未知"一样不会拦，
        # 只是把"没有限制"如实说出来（青岛山炮台 4/1-10/31 段就是这个形态，
        # 夏季周一照常开门）。
        for window in windows_seen:
            if window not in covered:
                rules.append({"months": window, "open": None, "unrestricted": True})
    return rules


def _verdict(opening, day):
    """(三态, 强度)；强度只用于区分"明文写了闭馆"与"开放日里没列出今天"。"""
    when = _as_date(day)
    if when is None:
        return None, None
    rules = rules_of(opening)
    if not rules:
        return None, None
    hit = [r for r in rules if _in_window(r["months"], when.month, when.day)]
    if not hit:
        return None, None
    weekday = when.weekday()
    for rule in hit:
        if rule.get("closed") and weekday in rule["closed"]:
            return True, "explicit"
    opens = [rule["open"] for rule in hit if rule.get("open")]
    if not opens:
        # 命中的窗口只写了时段、没写星期限制 -> 开放；连窗口都没有 -> 真不知道。
        if any(rule.get("unrestricted") for rule in hit):
            return False, None
        return None, None
    # 任一命中的开放日集合包含今天 → 开放；只有全部都不含今天才判闭馆，
    # 这种是靠"没列出"推出来的，强度标 inferred，不能当明示用。
    if all(weekday not in days for days in opens):
        return True, "inferred"
    return False, None


def closed_on(opening, day):
    """三态：True 闭馆 / False 明确开放 / None 资料不足不判定。"""
    return _verdict(opening, day)[0]


def closure_strength(opening, day):
    """"explicit" 明文闭馆 / "inferred" 开放日未列出推断 / None 未判闭馆。"""
    return _verdict(opening, day)[1]


def closed_reason(opening, day):
    """给用户的说明；仅在 closed_on 为 True 时有值。"""
    state, strength = _verdict(opening, day)
    if state is not True:
        return None
    when = _as_date(day)
    if strength == "inferred":
        note = "资料列出的开放日不含%s，推断当天不开放" % WEEKDAY_NAMES[when.weekday()]
    else:
        note = "资料显示%s闭馆，当天不开放" % WEEKDAY_NAMES[when.weekday()]
    if re.search(_HOLIDAY_EXCEPT, str(opening or "")):
        note += "（法定节假日除外）"
    return note
