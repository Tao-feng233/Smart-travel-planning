"""Recommendations responsibilities; tool schemas own field contracts."""

RECOMMEND = (
    "评估给定真实候选，结合旅行天数、体验范围、位置、偏好、同行需求和适用日期天气推荐组合及备选。"
    "recommendation_policy.target是候选目标，不表示全部必去；资料足够时推荐达到目标的集合，大型景区与小地点按合理体验取舍。"
    "候选不足说明，不编造ID。"
    "地图评分不是实时热度；设施、票种、房型景观等属性须有资料依据。"
    "parent_relations中的父景区是范围，避免父项和子地点同时作为独立必游而重复估时。"
    "酒店位置比较使用实际路线；餐饮考虑餐次与附近活动。"
    "只使用有覆盖日期的天气。"
    "推荐时段服从用户固定安排，夜间游览须有开放依据，未知日期不编造。"
    "返回JSON：recommendations数组含id、reason、role(primary/alternative)、evidence_ids；可附visit_date、visit_period、timing_reason；summary为简短比较，coverage_note说明集合与行程的匹配。"
    "理由突出相关特色和取舍，不重复已有的费用/营业待核实提示，不向用户展示内部字段。"
)

CHOOSE = (
    "用户已确认指定范围的代选授权。"
    "从给定候选ID选择，结合偏好、位置、日期、同行需求、参考费用和已有选择；餐饮考虑当前餐次，尽量避免重复。"
    "禁止代选车票机票。"
    "selection_policy说明选择数量与范围；景点组合不为填满日期堆积活动。"
    '返回JSON {"ids":["候选ID"],"reason":"简短选择理由"}。'
)
