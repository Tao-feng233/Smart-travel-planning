"""按城市取站点清单，供旅行信息表单的"到达站/返程站"下拉使用。

数据来源：高德 POI 检索。实测（洛阳/郑州）分类是准的：
    category=train_station → 洛阳龙门站、洛阳东站、洛阳北站、洛阳站、关林站…
    category=airport       → 洛阳北郊机场、洛阳北郊机场航站楼…
注意不要用 keywords="高铁站"：那会命中楼盘、民宿、辅导班等无关结果。

站点清单与具体行程无关（同一城市短期内不变），因此走既有 cache 表并给较长
有效期，避免每次打开表单都消耗一次高德调用。
"""

from app.integrations import tools
from app.persistence import storage

# 站点类别 -> 高德分类与展示名
KINDS = {
    "train": ("train_station", "火车站"),
    "flight": ("airport", "机场"),
}

# 站点清单变化很慢，给 30 天；与"实时票价"这类需要短缓存的数据不同。
TTL = 30 * 24 * 3600


def kind_for(vehicle):
    """出行方式 -> 站点类别；自驾或未知返回 None（自驾不需要站点）。"""
    if vehicle in ("train", "highspeed"):
        return "train"
    if vehicle == "flight":
        return "flight"
    return None


# 明显的非站点名，过滤掉以免污染下拉。实测高德会把公交站、地铁站、客运站、
# 已关闭的机场一并返回，例如「洛阳师范学院西门(公交站)」「郑州客运南站」
# 「青岛流亭国际机场(已关闭)」，都必须排除。
_NOISE = ("公交", "地铁", "客运", "长途汽车", "汽车站", "枢纽站",
          "广场", "酒店", "宾馆", "民宿", "公寓", "辅导", "培训", "托管",
          "幼儿园", "学校", "商店", "超市", "暂停营业", "已关闭", "航站楼",
          "停车场", "售票", "候机楼", "游客中心")


def _accepted(name, kind):
    """按类别判断是否真的是一个可乘降的站点。

    火车：必须以「站」结尾，且不含噪音词（洛阳站 / 洛阳龙门站 / 郑州东站）。
    飞机：必须含「机场」且不含噪音词；航站楼、已关闭/暂停营业的排除
          （青岛胶东国际机场 保留，青岛流亭国际机场(已关闭) 排除）。
    """
    if any(bad in name for bad in _NOISE):
        return False
    if kind == "train":
        return name.endswith("站")
    if kind == "flight":
        return "机场" in name
    return False


def _clean(rows, city, kind):
    out, seen = [], set()
    for row in rows or []:
        name = str((row or {}).get("name") or "").strip()
        if not name or name in seen or not _accepted(name, kind):
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "address": str((row or {}).get("address") or ""),
                # 城市名开头的排前面，便于用户先看到本市主要站点
                "primary": name.startswith(str(city or "")),
            }
        )
    out.sort(key=lambda x: (not x["primary"], -len(x["name"])))
    return out


async def list_stations(city, kind, *, tool=None):
    """返回 [{"name", "address", "primary"}, ...]；city/kind 非法时返回 []。"""
    city = str(city or "").strip()
    if not city or kind not in KINDS:
        return []
    category, _label = KINDS[kind]
    key = storage.cache_key("stations", {"city": city, "kind": kind})
    old = storage.cached(key)
    if old is not None:
        return old
    call = tool or tools.local_tool
    try:
        result = await call(
            "search_places",
            {"city": city, "keywords": "车站" if kind == "train" else "机场",
             "category": category, "page_size": 20},
        )
    except Exception:
        # 查询失败不阻断表单：前端会退化为可手动输入
        return []
    rows = _clean(result.get("items", []), city, kind)
    if rows:
        storage.put_cache(key, rows, TTL)
    return rows
