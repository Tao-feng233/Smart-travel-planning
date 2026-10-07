"""统一时间契约：抵达可用时刻与返程准备时刻只在这里计算。

设计约束（《成员三任务说明》第一批与第二批）：

* 时长单位统一为分钟；事件区间左闭右开。
* 硬条件只有班次时刻、预约、用户明确日期/时段；站点接驳、候车/值机、
  出站取行李都是可调整估计，必须带 ``basis``（依据）与 ``status``。
* 未知不等于零，也不等于"已核实"：缺少坐标或路线结果时返回
  ``needs_check`` 并列出 ``unverified``，由业务层展示为待核实。
* 站点/机场实体的定位由协调者负责；本模块只接受已经查到的坐标与路线
  结果，不猜测，也不新增一套供应商调用。
* 本模块不写数据库、不依赖 MySQL，纯函数便于用测试夹具驱动。

调用方约定：``route_minutes`` 是已查询到的道路耗时（分钟）。查询失败、
缺坐标、未返回方案时传 ``None``，由本模块给出待核实的可调整估计。
"""
from .providers import DataError  # 调用方复用统一错误类型；本模块自身不抛错

# ---------------------------------------------------------------------------
# 语义稳定的枚举
# ---------------------------------------------------------------------------
STATUS_VERIFIED = 'verified'      # 依据来自已查询的路线与已确认班次
STATUS_ESTIMATED = 'estimated'    # 有依据的可调整估计，必须展示依据
STATUS_NEEDS_CHECK = 'needs_check'  # 关键依据缺失，展示为待核实

UNITS = 'minutes'
TIMEZONE = 'Asia/Shanghai'
SCHEMA_VERSION = 1

MODE_FLIGHT = 'flight'
MODE_TRAIN = 'train'
MODE_OTHER = 'other'

# ---------------------------------------------------------------------------
# 可调整的估计值：集中在一处，便于协调者按承运规则核对后替换
# 这里不是"接口事实"，只是规划假设，全部会以 estimated/needs_check 输出。
# ---------------------------------------------------------------------------
EXIT_AND_BAGGAGE_MINUTES = 30          # 出站、取行李、找接驳
DEFAULT_CONNECTION_BUFFER_MINUTES = 20  # 接驳机动
# 候车/值机要求：按交通方式拟定的估计值，需按承运规则核实后替换。
WAIT_REQUIREMENTS = {
    MODE_FLIGHT: (120, '航空公司普遍建议国内航班提前约2小时到达机场'),
    MODE_TRAIN: (30, '高铁/动车一般建议提前约30分钟到达车站'),
    MODE_OTHER: (45, '普通列车一般建议提前约45分钟到达车站'),
}
# 旧版本固定使用的"提前120分钟"上限：只在关键依据缺失、仅用于兜底时使用，
# 且必须输出 needs_check，不能作为已核实结论。
FALLBACK_PREPARATION_MINUTES = 120
# 旧版本固定使用的"抵达+90分钟"：同上，仅作缺依据时的兜底。
FALLBACK_ARRIVAL_BUFFER_MINUTES = 90


def transport_mode(transport):
    """从班次记录判断交通方式：只依据已保存的 kind/名称，不做推断性猜测。"""
    if not isinstance(transport, dict):
        return MODE_OTHER
    kind = str(transport.get('kind') or '').lower()
    if kind in ('flight', 'plane', 'air'):
        return MODE_FLIGHT
    if kind in ('train', 'rail'):
        return MODE_TRAIN
    name = str(transport.get('name') or '')
    station = str(transport.get('arrival_station') or transport.get('departure_station') or '')
    if '机场' in name or '机场' in station or '航站楼' in station:
        return MODE_FLIGHT
    if any(token in name for token in ('G', 'D', 'C')) and name[:1].isalpha():
        return MODE_TRAIN
    if '站' in station:
        return MODE_TRAIN
    if kind:
        return MODE_OTHER
    return MODE_OTHER


def wait_requirement(mode):
    """返回 (分钟, 依据)。unknown 时用最大估计并标为待核实依据。"""
    return WAIT_REQUIREMENTS.get(mode, WAIT_REQUIREMENTS[MODE_OTHER])


def _result(minutes, status, basis, unverified=(), evidence=()):
    return {'minutes': int(max(0, minutes)), 'status': status, 'basis': basis,
            'unverified': list(unverified), 'evidence_ids': list(evidence),
            'unit': UNITS, 'timezone': TIMEZONE}


def _round_down(minutes, step=5):
    return int(max(0, minutes) // step * step)


def arrival_ready(transport, route_minutes, exit_minutes=None, buffer_minutes=None):
    """抵达后可以开始活动的最早时刻（相对班次到达时刻的分钟数）。

    组成：到达时刻 + 出站/取行李估计 + 到首站或住宿的路线 + 机动。
    ``route_minutes`` 为 None 表示路线尚未核实。
    """
    exit_minutes = EXIT_AND_BAGGAGE_MINUTES if exit_minutes is None else int(exit_minutes)
    buffer_minutes = DEFAULT_CONNECTION_BUFFER_MINUTES if buffer_minutes is None else int(buffer_minutes)
    unverified = []
    route_known = route_minutes is not None
    route_minutes = 0 if route_minutes is None else int(route_minutes)
    if route_known:
        # 关键依据齐备：出站估计 + 实查路线 + 机动，逐项可核对。
        total = route_minutes + exit_minutes + buffer_minutes
        parts = ['到达时刻', f'出站与取行李估计{exit_minutes}分钟',
                 f'到首站或住宿道路耗时{route_minutes}分钟', f'接驳机动{buffer_minutes}分钟']
    else:
        # 缺站点坐标或路线结果：保留原有保守估计，但必须标为待核实，
        # 不把未知当零，也不声称已经核实。
        total = FALLBACK_ARRIVAL_BUFFER_MINUTES
        parts = ['到达时刻', f'出站、接驳与到首站路线合计按{FALLBACK_ARRIVAL_BUFFER_MINUTES}分钟保守估计（沿用旧口径待替换）']
        unverified.append('站点或机场到首站/住宿的道路耗时尚未查询')
    status = STATUS_VERIFIED if not unverified else STATUS_NEEDS_CHECK
    return _result(total, status, '；'.join(parts), unverified)


def return_preparation(transport, route_minutes, wait_minutes=None, buffer_minutes=None):
    """返程日需要提前多少分钟从最后一项活动离开，才能赶上返程班次。

    组成：末站/末点到车站或机场的道路耗时 + 候车/值机要求 + 机动。
    ``route_minutes`` 为 None 表示末点到车站的路线尚未核实。
    """
    mode = transport_mode(transport)
    default_wait, wait_basis = wait_requirement(mode)
    wait_minutes = default_wait if wait_minutes is None else int(wait_minutes)
    buffer_minutes = DEFAULT_CONNECTION_BUFFER_MINUTES if buffer_minutes is None else int(buffer_minutes)
    unverified = []
    route_known = route_minutes is not None
    route_minutes = 0 if route_minutes is None else int(route_minutes)
    if route_known:
        total = route_minutes + wait_minutes + buffer_minutes
        parts = [f'末站到车站或机场道路耗时{route_minutes}分钟',
                 ('值机' if mode == MODE_FLIGHT else '候车') + f'{wait_minutes}分钟（{wait_basis}）',
                 f'接驳机动{buffer_minutes}分钟']
    else:
        # 原有固定"提前120分钟"仅作缺依据时的兜底，并明确标为待核实。
        total = FALLBACK_PREPARATION_MINUTES
        parts = [f'末站到车站、候车或值机与机动合计按{FALLBACK_PREPARATION_MINUTES}分钟保守估计（沿用旧口径待替换）']
        unverified.append('最后一站到车站或机场的道路耗时尚未查询')
    status = STATUS_VERIFIED if not unverified else STATUS_NEEDS_CHECK
    return _result(total, status, '；'.join(parts), unverified)


def return_cutoff(departure_minutes, preparation):
    """返程日最后一项活动必须结束的最晚分钟数（不含接驳）。"""
    minutes = preparation.get('minutes') if isinstance(preparation, dict) else int(preparation)
    return _round_down(int(departure_minutes) - int(minutes or 0))


def arrival_start(day_start_minutes, arrival_minutes, ready):
    """抵达日实际开始游玩的分钟数：不早于每日开始，也不早于抵达准备完成。"""
    ready_minutes = ready.get('minutes') if isinstance(ready, dict) else int(ready)
    return _round_down(max(int(day_start_minutes), int(arrival_minutes) + int(ready_minutes or 0)))


def transfer_note(preparation, label='前往车站或机场'):
    """给 transfer_plan 事件的说明文本：区分已核实部分与待核实部分。"""
    status = preparation.get('status')
    basis = preparation.get('basis') or ''
    if status == STATUS_VERIFIED:
        return f'{label}：已按核对结果预留{basis}。'
    missing = '、'.join(preparation.get('unverified') or [])
    suffix = f'；待核实：{missing}' if missing else ''
    return f'{label}：{basis}，为可调整估计，不是承运方承诺{suffix}。'


def station_place(workspace, transport, key):
    """查找车站/机场实体：只使用已有候选坐标，找不到就返回空壳对象。

    站点实体的定位由协调者负责；这里不调用供应商，也不猜坐标。
    """
    name = (transport or {}).get(key) or ''
    if not name:
        return None
    catalog = (workspace or {}).get('catalog') or {}
    wanted = str(name)
    from .locations import coordinate
    for place in catalog.values():
        if not isinstance(place, dict):
            continue
        if place.get('name') == wanted and coordinate(place.get('location')):
            return {**place, 'location_status': place.get('location_status') or 'verified'}
    return {'id': 'station:' + wanted, 'kind': 'station', 'name': wanted,
            'location': None, 'location_status': 'needs_coordinator', 'source': None}
