"""往返交通信息是否齐备。

按用户要求：到达时间与返程时间**必填**，到达站与返程站也必填；
只有出行方式为「自驾」时才不需要这些字段。

这里刻意不放在 requirements.update_requirements() 里做硬校验：
模型与多个既有流程都会分步写入这些字段，逐步校验会把中间状态误判为缺项。
改为提供一个显式校验函数，由"生成计划"与"旅行信息表单提交"两个
真正需要拦住的入口调用（用户选择的是强必填：填了才允许生成计划）。
"""

from app.core.errors import DataError

# 出行方式取值 -> 展示名
VEHICLE_LABELS = {
    "train": "火车",
    "highspeed": "高铁",
    "flight": "飞机",
    "drive": "自驾",
}

# 非自驾时必填的字段 -> 缺失时的说明
REQUIRED_NON_DRIVE = (
    ("arrival_station", "到达站"),
    ("arrival_time", "到达时间"),
    ("return_station", "返程站"),
    ("return_time", "返程时间"),
)


def vehicle_of(requirements):
    """取出行方式；老数据没有该字段时按 intercity_mode 折算。"""
    r = requirements or {}
    vehicle = r.get("intercity_vehicle")
    if vehicle in VEHICLE_LABELS:
        return vehicle
    return "drive" if r.get("intercity_mode") == "self_drive" else "highspeed"


def is_drive(requirements):
    return vehicle_of(requirements) == "drive"


def missing_fields(requirements):
    """非自驾时缺哪些必填项。返回 [(字段名, 展示名), ...]。"""
    r = requirements or {}
    if is_drive(r):
        return []
    return [
        (key, label)
        for key, label in REQUIRED_NON_DRIVE
        if not str(r.get(key) or "").strip()
    ]


def describe_missing(requirements):
    """缺项的可读描述；齐备时返回空串。"""
    missing = missing_fields(requirements)
    if not missing:
        return ""
    return "、".join(label for _, label in missing)


def require_complete(requirements):
    """校验往返交通是否齐备；缺项则抛 DataError。

    用于"生成计划"这类必须拦住的动作。错误信息里带上具体缺哪几项，
    便于前端直接显示、用户知道去补什么。
    """
    missing = missing_fields(requirements)
    if not missing:
        return
    vehicle = VEHICLE_LABELS.get(vehicle_of(requirements), "该出行方式")
    raise DataError(
        "出行方式为"
        + vehicle
        + "时，请先填写："
        + "、".join(label for _, label in missing)
        + "。也可以把出行方式改为自驾，无需填这些。",
        context={"phase": "transport", "missing": [k for k, _ in missing]},
    )
