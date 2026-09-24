# 可替换数据Provider架构 v0.4

## 1. 目标

先用Mock数据跑通全部业务；获得真实数据后只替换Provider，不修改LangGraph、规划器、验证器、GuideComposer和Vue。

## 2. 分层

```text
业务模块
    ↓
DataService / MCP工具
    ↓
Provider接口
├── MockProvider
├── SnapshotProvider（MySQL固定数据）
├── LiveApiProvider（实时API）
└── HybridProvider（实时优先、快照降级、缓存复用）
    ↓
统一Contract对象
```

## 3. 数据模式

```text
DATA_MODE=MOCK
全部使用fixture；输出DataAssuranceStatus.MOCK

DATA_MODE=SNAPSHOT
只使用清洗后存入MySQL/Chroma的数据

DATA_MODE=LIVE
优先请求实时接口；不允许静默使用Mock

DATA_MODE=HYBRID
实时接口 + 缓存 + MySQL快照；最终推荐模式
```

## 4. Provider接口

```text
DestinationProvider
ResourceProvider
FactProvider
IntercityProvider
RouteProvider
WeatherProvider
PreparationRuleProvider
KnowledgeProvider
```

所有Provider返回`CONTRACTS.md`对象，不把第三方原始响应直接传给业务层。

## 5. Hybrid读取流程

```text
读取MySQL快照
→ 检查valid_until和请求日期
→ 数据新鲜则直接使用
→ 过期且Live Provider可用则请求实时数据
→ 保存原始响应
→ 清洗、归一化和验证
→ 写入FactRecord/缓存
→ API失败则使用最近快照并标记DEGRADED
→ 无快照则返回DATA_MISSING
```

Mock只能在`RunMode.DEMO`或显式测试中使用。

## 6. 按变化速度选择方式

| 数据 | 推荐方式 |
|---|---|
| 目的地、区域、体验标签 | 预先整理到MySQL/Chroma |
| 景点坐标和基本属性 | MySQL快照 |
| 开放、票价、预约 | MySQL快照 + 定期/按需刷新 |
| 酒店、餐厅基本候选 | MySQL快照；有接口再刷新 |
| 路线和通勤 | 实时API + 短TTL缓存；人工矩阵降级 |
| 天气 | 实时API + 缓存；Mock仅演示 |
| 实时库存和余票 | 有合法接口再接入，否则UNKNOWN |

## 7. 配置与依赖注入

```env
DATA_MODE=MOCK
ALLOW_MOCK_IN_DEMO=true
ALLOW_STALE_SNAPSHOT=true
ROUTE_PROVIDER=mock
WEATHER_PROVIDER=mock
```

应用启动时由ProviderFactory读取配置并注入DataService。业务代码禁止直接实例化第三方SDK。

## 8. 数据缺失与无解

```text
DATA_MISSING
知识库或Provider没有必要资料

NO_FEASIBLE_PLAN
资料存在，但无法满足用户约束
```

两者必须返回不同错误和用户提示。

## 9. Provider契约测试

同一组测试必须对Mock、Snapshot和Live实现运行：

- 返回对象可通过Pydantic校验。
- 实体ID和来源字段存在。
- 过期、未知、模拟状态正确标记。
- 第三方错误能够转换为统一错误。
- 业务模块无需根据Provider类型写分支。

