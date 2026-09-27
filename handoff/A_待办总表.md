# 给 A 的待办总表（数据 / RAG / MCP）

> 更新时间：2026-09-27 · main = `3a5805c`（C1–C7 已完成，三条线代码都在 main 上）
> 一句话：**C 线的链路已经全部写完并测过，现在只差你的数据——真实数据一到位，
> 端到端立刻能演示；在那之前，整条链路对真实数据只会停在「明确的资料不足」。**

## 一、必修（不做，P0 演示跑不通）

| # | 事项 | 现状（实测） | 为什么卡住 |
|---|---|---|---|
| 1 | **住宿候选** `LODGING` | 0 个 | `ItineraryPlan.stay_segments` 与 `DayPlan.stay_segment_id` 都是必填，没有住宿就产不出合法行程 |
| 2 | **住宿区域** `LODGING_AREA` | 0 个 | `CONTRACTS.md` §15：「P0 完成住宿区域和人工整理候选」 |
| 3 | **景点间路线** | 只有 2 条且单向 | P0 要求行程含交通时间；缺的那几段 C4 只能记 `DATA_UNKNOWN` |
| 4 | **返程城际** | 0 条（去程有 1 条） | 攻略「抵达与返程」那节的 `ReturnPlan` 需要返程班次 |
| 5 | **天气覆盖整段行程** | 只覆盖成都 10-02/03/04 | 影响 B6 的「准备提醒」；缺日会抛 `DataMissingError` |
| 6 | **车站-住宿 路线** | 0 条 | `ArrivalPlan` / `ReturnPlan` 的时长与费用必填，C 不会用 `door_to_door_minutes` 硬凑 |

## 二、数据要求（照做就不用返工）

- 住宿候选字段：`resource_id`、`destination_id`、`name`、`address`、`lodging_type`、
  `lodging_area`、`price_range`（`min_amount`/`max_amount`）、`commute_summary`；
  住宿区域：`resource_id`、`destination_id`、`name`、`area_type`、`nearby_transport`、`food_convenience`。
- **主键统一用 `resource_id`**（Q4 已定）；外部 `hotel_id` / `lodging_id` 在你这边归一化，不要漏。
- 路线要**双向**都给（`poi→poi`、`poi→餐厅`、`住宿→景点`、`车站→住宿`），
  每条含 `duration_minutes`、`distance_km`、`estimated_cost`（`Money`，费用缺失 C 会报缺）。
- 天气尽量覆盖演示行程全期（10-02 ~ 10-06）。
- 缺数据时**宁可返回空，也不要编**；C 线会把空转成明确的降级提示。

## 三、口径与工程要求

- `get_weather` 缺日期时抛的是自定义 `DataMissingError`：请写进 README/报告；
  C 已经 try/except 兜住，但别人接你的 Provider 会踩。
- 你新增的 `mcp[cli]>=2.0,<3.0` 已处理成「缺 SDK 自动 skip」，**不要再改回强制导入**。
- 不要修改 `backend/app/schemas/`、`contracts/`、`fixtures/`；需要新字段先提，等三人确认。
- `V04MockMCPProvider` 是**你的替换点**：类名与 9 个方法签名不要变，C 的图直接调它。

## 四、验收方式（自己先跑，再叫我或 B 复核）

```powershell
python tools/check_a_data.py        # 现在是 7 项里 6 项没到位；全 OK 时退出码为 0
cd backend && python -m pytest      # 基线：285 passed, 1 skipped
```

补完 1、2、6 之后，下面这条链路就能真实跑通（现在用测试替身已跑通）：

```text
建会话 → 从上海出发10月2-6号2人预算5000想去成都 → 确认 → 排出行程 → 验证 VALID
→ 七部分攻略 → 确认攻略（锁节点）→ 说「今天下雨了」→ 只重排当天 → 新版本
```

## 五、原有任务（不阻塞 P0 演示，按计划推进）

- 真实 Provider 替换 Mock（MySQL / Chroma / 实时路线与天气）
- `hotel_id` / `lodging_id` → `resource_id` 归一化（Q4 已定）
- 数据源可行性表（A6）、测试 fixture（A7）
