"""景区开放时间解析与排程约束。

数据来源：候选景点的 `opening` 字段（高德"地图当前营业资料，出游日期需核实"）。
真实格式样本：
  周一至周日 00:00-24:00
  8:30-18:00,16:00停止售票,网络票停止换票
  3月至6月,9月至11月 周一至周日 07:00-17:30；7月至8月 周一至周日 06:00-19:00；12月,1月至2月 周一至周日 07:30-17:00
  5月至10月:周二至周日:09:00-17:00(16:30停止入场),11月至次年4月:09:00-16:30(16:00停止入场法定节假日除外)
  01/01-06/30 09:00–18:00开放 最晚售票17:00；07/01-08/31 08:30–18:30开放 最晚售票17:30

设计取舍：
* 资料是"地图当前营业资料，出游日期需核实"，可能含季节性多时段。这里取**所有时段的并集**作为
  最早开门/最晚关门，并取**最严的停止入场时刻**，避免凭空挑一个季节性时段而误判；
  拿不准时宁可不拦（返回 (None,None)），也不编造结论。
* 标为 24 小时的通常是"这片区域没有大门"（海边、广场、公园），不代表半夜适合游览，
  因此给非夜市类的 24 小时地点加一个"不排到傍晚之后"的上界。
"""
import re
from datetime import date

# 夜市、灯光秀等本就适合夜间的地点
NIGHT_HINTS = ('夜市', '夜景', '灯光', '夜游', '酒吧', '演出', '秀场', '啤酒街', '夜宵')
# 非夜市类地点最晚结束时刻（分钟）
EVENING_LIMIT = 18 * 60 + 30

_TIME = re.compile(r'(\d{1,2}):(\d{2})')
_RANGE = re.compile(r'(\d{1,2}):(\d{2})\s*[-–~至]\s*(\d{1,2}):(\d{2})')
# 两种顺序都出现："停止入场16:30" 与 "16:30停止入场"
_LAST_WORDS = r'最晚(?:进入|售票|入场|入园)|停止(?:入场|售票|入园|检票|换票)'
_LAST_ENTRY = re.compile(r'(?:' + _LAST_WORDS + r')\s*[:：]?\s*(\d{1,2}):(\d{2})')
_LAST_ENTRY_BEFORE = re.compile(r'(\d{1,2}):(\d{2})\s*(?:' + _LAST_WORDS + r')')


def _minutes(hour, minute):
    return int(hour) * 60 + int(minute)


def _full_day(text):
    return bool(re.search(r'00:00\s*[-–~至]\s*24:00', text)) or '全天开放' in text


def parse(opening):
    """返回 (最早开门, 最晚关门, 最晚进入)；无法解析的项为 None。

    取所有时段的并集与最严停止入场，避免在季节性资料里挑错时段。
    """
    if not opening:
        return None, None, None
    text = str(opening)
    ranges = [(_minutes(a, b), _minutes(c, d)) for a, b, c, d in _RANGE.findall(text)]
    if _full_day(text):
        opens, closes = 0, 24 * 60
    elif ranges:
        opens = min(x[0] for x in ranges)
        closes = max(x[1] for x in ranges)
    else:
        return None, None, None

    # 先在"剥掉所有时间区间"的副本上找停止入场时刻：
    # 否则 '09:00-17:00 最晚进入16:30' 会把关门时刻 17:00 也算成停止入场。
    stripped = _RANGE.sub(' ', text)
    entries = [(_minutes(a, b)) for a, b in _LAST_ENTRY.findall(stripped)]
    entries += [(_minutes(a, b)) for a, b in _LAST_ENTRY_BEFORE.findall(stripped)]
    last = min(entries) if entries else None
    # 关门时刻也可能是入场截止（资料只写一个时刻时保守处理）
    if last is None and closes and closes < 24 * 60:
        last = closes
    return opens, closes, last


def is_night_venue(name):
    return any(h in str(name or '') for h in NIGHT_HINTS)


def allowed_end(opening, name=''):
    """当天最晚结束时刻（分钟）。

    24 小时开放且非夜市类 → 按傍晚收尾，避免把海边礁石、广场排到深夜。
    """
    opens, closes, _ = parse(opening)
    if closes is None:
        return None
    if closes >= 24 * 60 and not is_night_venue(name):
        return EVENING_LIMIT
    return closes


def check(opening, name, start, duration):
    """判断某景点能否在 [start, start+duration] 安排。

    返回 (是否可行, 说明, 当天最晚结束时刻)。
    只依据已有资料判断；资料不足时返回可行且不设限。
    """
    if not opening:
        return True, '', None
    opens, closes, last = parse(opening)
    end = start + duration
    limit = allowed_end(opening, name)

    if last is not None and start > last:
        return False, '资料显示最晚进入 %s，安排到 %s 已过入场截止' % (_clock(last), _clock(start)), limit
    if opens is not None and start < opens:
        return False, '资料显示 %s 才开放，安排从 %s 开始尚早' % (_clock(opens), _clock(start)), limit
    if limit is not None and end > limit:
        return False, '资料显示最晚结束约 %s，安排到 %s 已超出' % (_clock(limit), _clock(end)), limit
    return True, '', limit


def _clock(minutes):
    minutes = max(0, min(24 * 60, int(minutes)))
    return '%02d:%02d' % (minutes // 60, minutes % 60)
