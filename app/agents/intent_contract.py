"""The main intent tool contract, separate from model instructions and execution.

Business capability descriptions live here once. Timeline edits reuse their own
schema so validation and the model see the same fields.
"""

from app.planning.timeline_tools import CHANGE_SCHEMA

FUNCTION = {
    "type": "function",
    "function": {
        "name": "submit_intent",
        "description": "理解用户的本轮需求，更新必要条件并选择下一项查询或规划动作。不要补造用户没说的条件。",
        "parameters": {
            "type": "object",
            "properties": {
                "recommend_count": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 24,
                    "description": "用户要求的景点候选数量。基础目标为每天至少2个；底层工具每批最多4个，不足时继续下一批。",
                },
                "requested_place": {
                    "type": "string",
                    "description": "用户明确点名的具体景点，必须如实填写原名称；泛指海滨、人文等主题不填写",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "discover_destinations",
                        "search_spots",
                        "spots_page",
                        "complete_spots",
                        "search_hotels",
                        "weather",
                        "train",
                        "flight",
                        "ticket",
                        "place_detail",
                        "plan",
                        "chat",
                        "select_room",
                        "complete_hotel",
                        "search_foods",
                        "meal_choice",
                        "visit_schedule",
                        "analyze_visits",
                        "adjust_timeline",
                        "refresh_routes",
                        "review_timeline",
                        "optimize_plan",
                        "complete_food",
                        "request_auto_selection",
                        "cancel_auto_selection",
                        "transport_arrangement",
                        "skip_hotel",
                        "undo",
                    ],
                    "description": "按目标产物选择：chat解释或回答；discover_destinations比较已有资料地区；search_spots查询/补充候选，spots_page仅浏览已有明确页码；complete_spots和complete_hotel保存用户明确的阶段完成；search_hotels查住宿，select_room保存明确房型；weather/train/flight/ticket/place_detail各查对应事实；search_foods查餐厅，meal_choice保存餐次，complete_food保存餐饮完成；visit_schedule保存用户明确指定的景点日期/时段/顺序；analyze_visits只分析游玩分配与建议时长；adjust_timeline实际修改建议时间轴；review_timeline只读检查安排合理性；refresh_routes查询已选地点间的交通方式与通行时间，刷新时间轴预览，不重排计划；plan首次生成完整计划，optimize_plan结合原计划或生成冲突修订完整计划；request_auto_selection申请代选范围确认，cancel_auto_selection取消；transport_arrangement保存自驾或自行安排往返。",
                },
                "patch": {
                    "type": "object",
                    "description": "仅本轮明确提供的条件，未提供不填写",
                    "properties": {
                        "intercity_mode": {
                            "type": "string",
                            "enum": ["self_drive", "self_arranged"],
                            "description": "往返城际交通由谁负责：自驾，或用户自行安排。本项目不出票，不提供“选班次”；用户自行安排时请一并提取到离站与时刻。",
                        },
                        "origin_station": {
                            "type": "string",
                            "description": "去程出发站名称，如“郑州东站”；用户未说就不填。",
                        },
                        "arrival_station": {
                            "type": "string",
                            "description": "去程到达站名称，如“洛阳龙门站”；用户未说就不填。",
                        },
                        "arrival_time": {
                            "type": "string",
                            "description": "去程到达精确时刻，HH:MM；只说时段就不要填这里。",
                        },
                        "arrival_period": {
                            "type": "string",
                            "enum": ["morning", "afternoon", "evening"],
                            "description": "去程到达时段；用户只给了大概时间时填这里。",
                        },
                        "return_station": {
                            "type": "string",
                            "description": "返程出发站名称；用户未说就不填（可能默认同到达站，但需用户确认）。",
                        },
                        "return_arrival_station": {
                            "type": "string",
                            "description": "返程到达站名称；用户未说就不填。",
                        },
                        "return_time": {
                            "type": "string",
                            "description": "返程开车精确时刻，HH:MM；只说时段就不要填这里。",
                        },
                        "return_period": {
                            "type": "string",
                            "enum": ["morning", "afternoon", "evening"],
                            "description": "返程出发时段；用户只给了大概时间时填这里。",
                        },
                        "intercity_ticket_cost": {
                            "type": "number",
                            "description": "往返交通费用合计（用户主动提供时才填）；未提供不填，系统不按零计入预算。",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "游玩最后一天（游玩区间含首尾）；住宿退房或次日离开写return_date，不扩大游玩区间。",
                        },
                        "local_trip": {"type": "boolean"},
                        "return_date": {
                            "type": "string",
                            "description": "用户明确修改正式返程安排时填写；只查询或比较其他日期的班次使用departure_date，不写入patch。不得覆盖旅行开始日期。",
                        },
                        "outbound_date": {
                            "type": "string",
                            "description": "用户明确修改正式去程安排时填写；只查询或比较其他日期的班次使用departure_date，不写入patch。区别于游玩开始日期。",
                        },
                        "food_preferences": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "city": {"type": "string"},
                        "origin": {"type": "string"},
                        "start_date": {"type": "string"},
                        "days": {
                            "type": "integer",
                            "description": "游玩天数，区别于提前抵达和离开日期；明确区间含首尾。",
                        },
                        "adults": {"type": "integer"},
                        "children": {"type": "integer"},
                        "child_ages": {"type": "array", "items": {"type": "integer"}},
                        "rooms": {"type": "integer"},
                        "budget": {"type": "number"},
                        "pace": {
                            "type": "string",
                            "enum": ["relaxed", "balanced", "packed"],
                        },
                        "transport_mode": {
                            "type": "string",
                            "enum": ["balanced", "walking", "transit", "driving"],
                            "description": "用户明确指定的市内交通偏好；少走路属于行动需求，不等于walking。",
                        },
                        "preferences": {"type": "array", "items": {"type": "string"}},
                        "hard_constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "companion_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "用户明确提到的同行人群及行动需求，如带老人、小孩、减少爬坡；不猜总人数或年龄。",
                        },
                        "midday_rest_minutes": {
                            "type": "integer",
                            "description": "仅用户明确午休分钟数时填写；明确不要午休可填写0，最多120。不把默认建议当用户要求。",
                        },
                        "day_start": {
                            "type": "string",
                            "pattern": "^(?:[01]\\d|2[0-3]):[0-5]\\d$",
                            "description": "用户明确的每日开始时刻 HH:MM",
                        },
                        "day_end": {
                            "type": "string",
                            "pattern": "^(?:[01]\\d|2[0-3]):[0-5]\\d$",
                            "description": "用户明确的每日结束时刻 HH:MM",
                        },
                    },
                    "additionalProperties": False,
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索景点名称或主题，最多4项",
                },
                "direction": {
                    "type": "string",
                    "enum": ["outbound", "return"],
                    "description": "交通查询方向，返程使用return",
                },
                "reject_current": {
                    "type": "boolean",
                    "description": "用户说当前景点都不想去、换一些时为true；只翻下一页时false",
                },
                "select_ids": {"type": "array", "items": {"type": "string"}},
                "remove_ids": {"type": "array", "items": {"type": "string"}},
                "stay_date": {
                    "type": "string",
                    "description": "选择酒店对应的入住夜晚 YYYY-MM-DD",
                },
                "stay_dates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户明确的多晚住宿分配；不自动覆盖其他夜晚",
                },
                "answer": {
                    "type": "string",
                    "description": "简短确认、解释或询问缺项。不宣称尚未执行的查询已完成。",
                },
                "keyword": {
                    "type": "string",
                    "description": "用户指定的酒店品牌、名称或住宿区域，原样用于酒店查询",
                },
                "room_id": {
                    "type": "string",
                    "description": "来自给定room_choices的房型报价ID",
                },
                "replace": {
                    "type": "boolean",
                    "description": "用户明确要求改选已有班次时为true",
                },
                "time_start": {"type": "string", "description": "出发时间段起点 HH:MM"},
                "time_end": {"type": "string", "description": "出发时间段终点 HH:MM"},
                "train_type": {
                    "type": "string",
                    "enum": ["all", "highspeed", "regular"],
                },
                "acknowledgement": {
                    "type": "string",
                    "description": "执行前回应本轮要求的一句简短确认，不宣称已完成查询或选择",
                },
                "include_food": {"type": "boolean"},
                "food_keywords": {"type": "array", "items": {"type": "string"}},
                "prefer_known": {"type": "boolean"},
                "auto_select": {
                    "type": "boolean",
                    "description": "班次仅展示候选，此字段始终为false",
                },
                "meal_mode": {"type": "string", "enum": ["chosen", "self", "remove"]},
                "meal_date": {"type": "string"},
                "meal_period": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner"],
                },
                "food_id": {"type": "string"},
                "anchor_id": {
                    "type": "string",
                    "description": "当前景点或酒店参照ID，用于餐饮查询",
                },
                "departure_date": {
                    "type": "string",
                    "description": "本轮班次查询条件，可以与已选安排不同；查询不修改正式日期或已选班次。用户选定新班次后再保存其实际日期。",
                },
                "visit_requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "date": {"type": "string"},
                            "period": {
                                "type": "string",
                                "enum": ["any", "morning", "afternoon", "evening"],
                            },
                            "clear": {"type": "boolean"},
                        },
                        "required": ["candidate_id"],
                    },
                    "description": "用户明确指定某景点哪天哪个时段游玩，使用真实ID和旅行日期；取消指定用clear。",
                },
                "visit_order": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户明确指定先后游玩顺序时，按顺序返回已选景点真实ID。使用visit_schedule；不可自动修改明确日期时段。",
                },
                "view": {
                    "type": "string",
                    "enum": [
                        "food",
                        "hotel",
                        "knowledge",
                        "map",
                        "plan",
                        "spot",
                        "transport",
                        "weather",
                    ],
                    "description": "本轮正在讨论的工作台主题。即使只是解释，也可指定景点spot、住宿hotel、天气weather、往返交通transport、计划plan或资料knowledge。没有明确主题则省略。",
                },
                "id": {
                    "type": "string",
                    "description": "要查询详情或门票的现有候选ID，必须来自目录，不猜造ID",
                },
                "visit_date": {
                    "type": "string",
                    "description": "门票查询的游玩日期YYYY-MM-DD，独立于旅行开始日期",
                },
                "preference_mode": {
                    "type": "string",
                    "enum": ["default"],
                    "description": "仅用户明确暂无偏好或希望默认/热门景点推荐时填写default；首次只提供目的地时不填写。",
                },
                "expand_spots": {
                    "type": "boolean",
                    "description": "用户希望继续推荐、更多相关景点时为true，配合search_spots补充新候选；不是翻已有页面。",
                },
                "page": {
                    "type": "integer",
                    "description": "仅浏览已有推荐的明确页码时填写，配合spots_page。",
                },
                "instruction": {
                    "type": "string",
                    "description": "用户本轮对完整计划书的修改要求",
                },
                "auto_mode": {"type": "string", "enum": ["remaining", "replace"]},
                "auto_categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["destination", "spots", "hotel", "food"],
                    },
                },
                "mission": {
                    "type": "object",
                    "properties": {
                        "objective": {
                            "type": "string",
                            "description": "用户本轮希望达成的具体目标，含本轮相对上文的变化",
                        },
                        "mode": {
                            "type": "string",
                            "enum": [
                                "consult",
                                "query",
                                "delegate",
                                "edit_plan",
                                "explain",
                                "act",
                            ],
                            "description": "用户意图摘要，不限定业务阶段。consult比较；query查事实或调用只读工具检查安排；explain仅凭已有信息说明原因，action=chat；act执行明确修改；edit_plan生成或修订计划，可先查候选并补齐用户授权的安排；delegate按明确委托代选。只有缺少重要条件、采用假设或需要超出委托范围时才询问。",
                        },
                        "scopes": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["destination", "spots", "hotel", "food"],
                            },
                        },
                        "multi_step": {
                            "type": "boolean",
                            "description": "完成目标是否需要根据工具结果继续决策；单一明确查询为false",
                        },
                        "generate_plan": {
                            "type": "boolean",
                            "description": "用户是否要求完成后生成计划书",
                        },
                    },
                    "required": [
                        "objective",
                        "mode",
                        "scopes",
                        "multi_step",
                        "generate_plan",
                    ],
                },
                "patch_evidence": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "patch每个字段在本轮用户消息中的原文依据，建议默认值不能放patch",
                },
            },
            "required": ["action", "patch", "answer", "mission", "patch_evidence"],
            "additionalProperties": False,
        },
    },
}

FUNCTION["function"]["parameters"]["properties"]["timeline_changes"] = CHANGE_SCHEMA
FUNCTION["function"]["parameters"]["properties"]["preference_updates"] = {
    "type": "object",
    "description": "用户明确追加、替换或移除旅行/餐饮偏好时使用；add追加，replace替换（空列表清空），remove移除列出的偏好。同一字段不要同时写入patch。",
    "properties": {
        field: {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["add", "replace", "remove"]},
                "values": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string"},
                },
            },
            "required": ["mode", "values"],
            "additionalProperties": False,
        }
        for field in ("preferences", "food_preferences")
    },
    "additionalProperties": False,
}
ACTIONS = set(FUNCTION["function"]["parameters"]["properties"]["action"]["enum"])
