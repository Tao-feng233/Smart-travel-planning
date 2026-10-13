"""用户填写的往返交通时刻：把「精确时刻 / 时段 / 未定」统一解析成可用的 datetime。

设计依据见 `往返交通改为用户填写-设计文档.md`：

- 日期由用户确定（start_date / days），**不能靠估算**，否则 `nights()` 排不出住宿；
- 时段必填、精确时刻选填 —— 让时刻永远有锚点，同时不逼用户编数字；
- 解析结果带 basis 标记（precise / period / unknown），供提示文案区分。

**为什么时段取「起点」**：取起点 → 窗口更窄 → 安排更保守。
用户实际比估算晚到也不会撞车。这与既有约定一致
（`app/planning/schedule.py` 里时段边界同样是 9:00 / 13:00 / 18:00）。

**为什么未定（留空）回落到 afternoon 而不是整天可用**：
按整天可用会出现「早上 9 点就能开始玩」的错误安排，
违背报告里「未知时间不会按零处理」的承诺。回落到下午是保守选择，且必须标注。
"""

from datetime import date, datetime, time, timedelta

# 时段起点与既有排程约定保持一致（上午 9:00 / 下午 13:00 / 晚上 18:00）。
PERIOD_START = {"morning": time(9, 0), "afternoon": time(13, 0), "evening": time(18, 0)}

PERIOD_LABEL = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}

# 未填写时段时使用的兜底时段（必须同时产生可见标注）。
FALLBACK_PERIOD = "afternoon"

BASIS_PRECISE = "precise"
BASIS_PERIOD = "period"
BASIS_UNKNOWN = "unknown"

# 方向 -> (requirements 里的时刻键, 时段键, 默认基准日期键)
DIRECTIONS = {
    "outbound": ("arrival_time", "arrival_period", "outbound_date"),
    "return": ("return_time", "return_period", "return_date"),
}


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None


def _parse_clock(value):
    """只接受 HH:MM 或 HH:MM:SS；不接受带日期的完整时间戳。"""
    text = str(value or "").strip()
    if not text or "T" in text or " " in text or len(text) > 8:
        return None
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def resolve(requirements, direction, *, base_date=None):
    """解析某方向的交通时刻。

    返回 ``(datetime | None, basis)``：

    * 精确时刻（``*_time`` 为 HH:MM）→ 与基准日期合成，basis = "precise"
    * 时段（``*_period`` 为 morning/afternoon/evening）→ 时段起点，basis = "period"
    * 两者都空 → 回落到 afternoon 起点，basis = "unknown"（调用方**必须**展示提示）
    * **连基准日期都没有 → (None, "unknown")**，因为日期不能估算
    """
    requirements = requirements or {}
    time_key, period_key, date_key = DIRECTIONS[direction]

    if base_date is None:
        base_date = _parse_date(requirements.get(date_key))
    else:
        base_date = _parse_date(base_date)
    if base_date is None:
        # 日期是地基：没有日期就不能合成时刻，否则会算错到别的日子上。
        return None, BASIS_UNKNOWN

    precise = _parse_clock(requirements.get(time_key))
    if precise is not None:
        return datetime.combine(base_date, precise), BASIS_PRECISE

    period = str(requirements.get(period_key) or "").strip()
    if period in PERIOD_START:
        return datetime.combine(base_date, PERIOD_START[period]), BASIS_PERIOD

    return datetime.combine(base_date, PERIOD_START[FALLBACK_PERIOD]), BASIS_UNKNOWN


def basis_of(requirements, direction, *, base_date=None):
    """只要 basis 标记，供提示文案使用。"""
    return resolve(requirements, direction, base_date=base_date)[1]


def note_for(requirements, direction, *, base_date=None):
    """返回该方向需要展示给用户的提示；无需提示时返回空字符串。

    三种「时刻缺失」的来源文案不同，不能混在一起（见设计文档第九节）：
    用户明确留空 / 有日期无时段 / 完全没有日期。
    """
    _, basis = resolve(requirements, direction, base_date=base_date)
    if basis == BASIS_PRECISE:
        return ""
    requirements = requirements or {}
    _, period_key, date_key = DIRECTIONS[direction]
    label = "到达" if direction == "outbound" else "返程"
    if _parse_date(requirements.get(date_key) or base_date) is None:
        return label + "日期尚未填写，该方向的时间窗口暂时无法核对。"
    period = str(requirements.get(period_key) or "").strip()
    if period in PERIOD_START:
        return (
            label
            + "时间按"
            + PERIOD_LABEL[period]
            + "估算（"
            + PERIOD_START[period].strftime("%H:%M")
            + "）；填上具体时刻可让首尾日安排更准确。"
        )
    return (
        label
        + "时间未定，已按下午到达预留（"
        + PERIOD_START[FALLBACK_PERIOD].strftime("%H:%M")
        + "）；建议填上时段或具体时刻后重新核对。"
    )


def default_return_date(requirements):
    """未填返程日期时的默认返程日。

    口径（已确认）：最后一晚 = 最后一个游玩日，
    因此默认返程日 = 最后一个游玩日的次日。

        start_date=2026-10-11、days=3 → 游玩日 10-11/12/13 → 默认返程日 10-14
    """
    requirements = requirements or {}
    start = _parse_date(requirements.get("start_date"))
    if start is None:
        return None
    try:
        days = int(requirements.get("days") or 0)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return start + timedelta(days=days)
