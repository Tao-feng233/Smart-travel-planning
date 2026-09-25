"""把用户自然语言转为 `TripProfileDraft` / `TripProfile`（v0.4 契约）。

⚠️ **本文件是 STUB**。按分工，需求提取属于 B 线（B2），
真实实现应由 LLM 完成结构化输出。C 线先用一套**规则式提取器**让 LangGraph
的“追问 → 补充 → 再解析”回路可以独立跑通；B 线完成后，
只需实现同一个 `TripProfileParser` 协议并在 `app/api/deps.py` 中替换。

设计约束：

* 本解析器**不提供任何旅游事实**，只把用户话里已有的信息填进契约对象；
* 无法识别的输入不猜测、不补全，缺失情况交给 `missing_fields` 判定后追问；
* 用户只是"提过一句"的偏好，按 `constraints` 的 `SOFT` 类型记录
  （`CONTRACTS.md` §2.1），不得写进 `FIXED`。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Mapping, Protocol

from app.schemas import (
    Constraint,
    DestinationRequest,
    Money,
    TripProfileDraft,
)

#: 中文数字，用于“三个人”“两天”这类表达。
_CN_NUM = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_INTEREST_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FOOD": ("美食", "吃", "小吃", "餐厅"),
    "CULTURE": ("人文", "文化", "历史", "博物馆", "古镇"),
    "NATURE": ("自然", "风景", "山水", "公园", "爬山"),
    "NIGHTLIFE": ("夜生活", "夜景", "酒吧"),
    "SHOPPING": ("购物", "逛街", "商场"),
    "FAMILY": ("亲子", "带孩子"),
}

_AVOIDANCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "HIGH_INTENSITY_HIKING": ("不想爬山", "不爬山", "爬不动", "不想徒步"),
    "CROWDED_PLACES": ("不想挤", "人太多", "避开人流"),
}

#: 软偏好 → `Constraint`（`kind = SOFT`）。字段名对齐 `TripProfile` 的真实字段，
#: 便于 C4 规划时把它翻译成可放宽的约束。
_SOFT_PREFERENCE_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("soft_late_start", "earliest_day_start", ("不想早起", "不要早起", "晚点起")),
    ("soft_less_walking", "mobility_constraints", ("少走路", "不想走太多")),
)

#: 预算"不能超"的表达 → `budget_flexibility = FIXED`。
_FIXED_BUDGET_WORDS = ("预算固定", "不能超过", "不能超", "最多", "上限")

#: 日期片段（"2026-10-06 / 2026年10月6日 / 10月6号 / 10/06"）。
#: 供"出发日期：X""返回日期：X""X 回来"这类**带标签**的表达复用。
_DATE_TOKEN = r"(?:\d{4}[-/年])?\d{1,2}[-/月]\d{1,2}[日号]?"


class TripProfileParser(Protocol):
    """B2 的替换点：实现同一协议即可被 LangGraph 直接使用。"""

    def parse(
        self,
        *,
        session_id: str,
        text: str,
        previous: TripProfileDraft | None,
        reference_date: date,
        known_destinations: Mapping[str, str] | None = None,
    ) -> TripProfileDraft: ...


class StubTripProfileParser:
    """规则式提取器（STUB，待 B 线替换）。"""

    def parse(
        self,
        *,
        session_id: str,
        text: str,
        previous: TripProfileDraft | None,
        reference_date: date,
        known_destinations: Mapping[str, str] | None = None,
    ) -> TripProfileDraft:
        base = (
            previous.model_copy(deep=True)
            if previous
            else TripProfileDraft(session_id=session_id)
        )
        base.session_id = session_id

        self._extract_departure_city(base, text)
        self._extract_duration_or_dates(base, text, reference_date)
        self._extract_travelers(base, text)
        self._extract_budget(base, text)
        self._extract_preferences(base, text)
        self._extract_destination(base, text, known_destinations or {})
        return base

    # --- 各字段的提取规则 ---------------------------------------------------

    @staticmethod
    def _extract_departure_city(profile: TripProfileDraft, text: str) -> None:
        patterns = (
            r"从([\u4e00-\u9fa5]{2,6}?)(?:出发|过去|出发去)",
            r"出发地[是：:]?\s*([\u4e00-\u9fa5]{2,6})",
            r"我(?:在|住在)([\u4e00-\u9fa5]{2,6})",
            r"([\u4e00-\u9fa5]{2,6}?)出发",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                profile.departure_city = match.group(1)
                return

    @staticmethod
    def _extract_duration_or_dates(
        profile: TripProfileDraft, text: str, reference_date: date
    ) -> None:
        start: date | None = profile.start_date
        end: date | None = profile.end_date

        # 先认"带标签"的日期：用户被追问"哪天回来"后，回答里往往只有一个日期，
        # 不做标签识别会把返回日期错当成新的出发日期（把已确认的 start 覆盖掉）。
        labeled_start = re.search(
            rf"出发(?:日期|时间)?[是：:\s]*({_DATE_TOKEN})", text
        )
        labeled_end = re.search(
            rf"(?:返回|回程)(?:日期|时间)?[是：:\s]*({_DATE_TOKEN})", text
        ) or re.search(rf"({_DATE_TOKEN})\s*(?:那天)?(?:回来|返回|回程)", text)
        labeled_start_date = (
            StubTripProfileParser._parse_token(labeled_start.group(1), reference_date)
            if labeled_start
            else None
        )
        labeled_end_date = (
            StubTripProfileParser._parse_token(labeled_end.group(1), reference_date)
            if labeled_end
            else None
        )
        if labeled_start_date is not None:
            start = labeled_start_date
        if labeled_end_date is not None:
            end = labeled_end_date

        explicit = list(
            re.finditer(
                r"(?:(\d{4})[-/年])?(\d{1,2})[-/月](\d{1,2})[日号]?", text
            )
        )
        parsed = [
            StubTripProfileParser._to_date(
                match.group(1), match.group(2), match.group(3), reference_date
            )
            for match in explicit
        ]
        parsed = [item for item in parsed if item is not None]

        if labeled_start_date is None and labeled_end_date is None:
            if len(parsed) > 1:
                start = parsed[0]
                end = parsed[-1]
            elif parsed:
                start, end = StubTripProfileParser._assign_single_date(
                    parsed[0], start, end, text
                )
            # “10月2-6号”：第二段只写了日
            compact = re.search(
                r"(\d{1,2})月(\d{1,2})[日号]?\s*[-~至到]\s*(\d{1,2})[日号]", text
            )
            if compact:
                start = StubTripProfileParser._to_date(
                    None, compact.group(1), compact.group(2), reference_date
                )
                end = StubTripProfileParser._to_date(
                    None, compact.group(1), compact.group(3), reference_date
                )
        else:
            # 有标签时**不能整段跳过无标签日期**：同一句话里可以既有
            # 「10月2号出发」（无标签）又有「返回日期：10月6号」（有标签）。
            # 只补标签没覆盖的那一侧，而且只在恰好剩一个日期时才敢认定，
            # 多出来的日期一律不猜（猜错比多问一轮更贵）。
            remaining = [
                item
                for item in parsed
                if item != labeled_start_date and item != labeled_end_date
            ]
            if len(remaining) == 1:
                if labeled_start_date is None:
                    start = remaining[0]
                elif labeled_end_date is None:
                    end = remaining[0]

        # 新的出发日把已有的返回日甩到了前面：清掉返回日让追问去补，
        # 否则 TripProfileDraft 会因为 end < start 直接校验失败。
        # `cleared_end` 是必要的：`end is None` 平时表示"这次没提到返回日"
        # （保持会话里已有的值），只有这里表示"主动清空"。
        cleared_end = False
        if start is not None and end is not None and end < start:
            end = None
            cleared_end = True

        days = re.search(r"(\d+|[一二两三四五六七八九十])\s*天", text)
        if days:
            count = StubTripProfileParser._to_int(days.group(1))
            if count and start is not None:
                end = start + timedelta(days=count - 1)

        if start is not None:
            profile.start_date = start
        if end is not None:
            profile.end_date = end
        elif cleared_end:
            profile.end_date = None

    @staticmethod
    def _assign_single_date(
        candidate: date, start: date | None, end: date | None, text: str
    ) -> tuple[date | None, date | None]:
        """只有一个日期、且没有任何标签时，判断它是出发日还是返回日。

        规则（顺序敏感，按用户真实说话方式设计）：

        1. 还没有出发日 → 就是出发日；
        2. 比已有出发日更晚：

           * 带「出发 / 动身」字样 → 用户是在**改出发日**（返回日由调用方
             按 `end < start` 清空，等追问补充）；
           * 没有 → 读作返回日（用户被追问"哪天回来"后直接报个日期）；

        3. 早于或等于已有出发日 → 意图不明，不猜，原样返回。
        """

        if start is None:
            return candidate, end
        if candidate > start:
            if re.search(r"出发|动身", text):
                return candidate, end
            return start, candidate
        return start, end

    @staticmethod
    def _parse_token(token: str, reference_date: date) -> date | None:
        """把 `10月6号` / `2026-10-06` 这类日期片段转成 `date`。"""

        match = re.fullmatch(
            r"(?:(\d{4})[-/年])?(\d{1,2})[-/月](\d{1,2})[日号]?", token.strip()
        )
        if not match:
            return None
        return StubTripProfileParser._to_date(
            match.group(1), match.group(2), match.group(3), reference_date
        )

    @staticmethod
    def _extract_travelers(profile: TripProfileDraft, text: str) -> None:
        count: int | None = profile.traveler_count
        match = re.search(r"(\d+|[一二两三四五六七八九十])\s*(?:个)?(?:人|大人)", text)
        if match:
            parsed = StubTripProfileParser._to_int(match.group(1))
            if parsed:
                count = parsed
        if "我们俩" in text or "两个人" in text:
            count = 2
        family = re.search(r"一家(\d|[一二两三四五六七八九十])口", text)
        if family:
            parsed = StubTripProfileParser._to_int(family.group(1))
            if parsed:
                count = parsed
        if count is not None:
            profile.traveler_count = count

        if any(word in text for word in ("老人", "父母", "爸妈", "长辈")):
            profile.mobility_constraints = _merge_list(
                profile.mobility_constraints, ["同行有老人，需控制步行强度"]
            )
        if any(word in text for word in ("腿脚不便", "不能走太多", "走不动")):
            profile.mobility_constraints = _merge_list(
                profile.mobility_constraints, ["行动不便，需减少步行与换乘"]
            )

    @staticmethod
    def _extract_budget(profile: TripProfileDraft, text: str) -> None:
        amount: float | None = None
        match = re.search(
            r"预算\s*(?:大概|大约|是|在|有|为)?\s*(\d+(?:\.\d+)?)\s*(万|千|k|K)?", text
        )
        if not match:
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*(万|千)?\s*(?:元|块钱|块|人民币)", text
            )
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            if unit in ("万",):
                value *= 10_000
            elif unit in ("千", "k", "K"):
                value *= 1_000
            amount = value
        else:
            # 中文数字金额："预算一万""预算五千"这类写法上面两条正则都吃不到
            cn = re.search(
                r"预算\s*(?:大概|大约|是|在|有|为)?\s*([一二两三四五六七八九十])\s*(万|千|百)",
                text,
            )
            if cn:
                base = _CN_NUM[cn.group(1)]
                unit = cn.group(2)
                amount = float(base * {"万": 10_000, "千": 1_000, "百": 100}[unit])

        if amount is not None:
            # v0.4：金额与"是否可协商"是两个字段（`Money` + `budget_flexibility`）
            profile.budget = Money(amount=amount, currency="CNY")
            if any(word in text for word in _FIXED_BUDGET_WORDS):
                profile.budget_flexibility = "FIXED"
            elif profile.budget_flexibility is None:
                profile.budget_flexibility = "NEGOTIABLE"

    @staticmethod
    def _extract_preferences(profile: TripProfileDraft, text: str) -> None:
        for tag, words in _INTEREST_KEYWORDS.items():
            if any(word in text for word in words):
                profile.interests = _merge_list(profile.interests, [tag])
        for tag, words in _AVOIDANCE_KEYWORDS.items():
            if any(word in text for word in words):
                profile.avoidances = _merge_list(profile.avoidances, [tag])
        if any(word in text for word in ("轻松", "慢节奏", "悠闲", "不赶")):
            profile.pace = "RELAXED"
        elif any(word in text for word in ("紧凑", "多去几个", "特种兵")):
            profile.pace = "INTENSE"

        for key, field_name, words in _SOFT_PREFERENCE_RULES:
            hit = next((word for word in words if word in text), None)
            if hit is None:
                continue
            profile.constraints = _merge_constraint(
                profile.constraints,
                Constraint(
                    constraint_id=f"c_{key}",
                    kind="SOFT",
                    field=field_name,
                    operator="CONTAINS",
                    value=hit,
                    source_text=hit,
                ),
            )

    @staticmethod
    def _extract_destination(
        profile: TripProfileDraft, text: str, known_destinations: Mapping[str, str]
    ) -> None:
        for name, destination_id in known_destinations.items():
            if name not in text:
                continue
            requests = list(profile.destination_requests)
            if not any(item.destination_id == destination_id for item in requests):
                requests.append(
                    DestinationRequest(
                        destination_id=destination_id,
                        name=name,
                        priority="HIGH",
                        fixed=True,
                        user_reason="用户明确提到该目的地",
                    )
                )
            profile.destination_requests = requests
            profile.destination_mode = "MULTIPLE" if len(requests) > 1 else "SINGLE"
            return

    # --- 工具方法 -----------------------------------------------------------

    @staticmethod
    def _to_int(raw: str) -> int | None:
        if raw.isdigit():
            return int(raw)
        return _CN_NUM.get(raw)

    @staticmethod
    def _to_date(
        year: str | None, month: str, day: str, reference_date: date
    ) -> date | None:
        try:
            parsed_year = int(year) if year else reference_date.year
            candidate = date(parsed_year, int(month), int(day))
        except ValueError:
            return None
        if year is None and candidate < reference_date - timedelta(days=1):
            # 用户没写年份且日期已过，按“明年的同一日期”理解
            try:
                candidate = candidate.replace(year=candidate.year + 1)
            except ValueError:
                return None
        return candidate


def _merge_list(existing: list[str], additions: list[str]) -> list[str]:
    merged = list(existing)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_constraint(existing: list[Constraint], item: Constraint) -> list[Constraint]:
    """同一条软偏好只保留一条（重复说"不想早起"不产生重复约束）。"""

    merged = [c for c in existing if c.constraint_id != item.constraint_id]
    merged.append(item)
    return merged
