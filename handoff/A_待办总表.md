# 给 A 的待办总表（数据 / RAG / MCP）

> 更新时间：2026-09-27 · 一句话：**你的成都 Mock 覆盖已合入 main，7 项数据检查 7/7 通过，端到端真链路跑通了。**

## 一、你的交付（已合入，谢谢）

11 个可检索 Mock 游玩地点 / 2 个住宿区域 + 4 个住宿候选 / 景点-餐厅-住宿-车站双向路线 /
上海→成都去程 + 成都→上海返程 / 2026-10-02~10-06 连续天气 / 资源与 evidence_id 修正 / 未改共享 Schema。

验证（C 侧复跑）：

```text
python tools/check_a_data.py                 → 7/7，退出码 0
python tools/check_b_flow.py --deps real      → 退出码 0（会话→追问→推荐→确认→七部分攻略→确认攻略→突发事件→新版本）
cd backend && python -m pytest                → 302 passed, 1 skipped
```

## 二、你报的三个 P0：处理结果

| 你报的问题 | 处理 |
|---|---|
| 返程查询方向错误 | ✅ 已修：返程改为查「目的地→出发地」（对称查询） |
| TravelLeg 没占时间轴 | ✅ 已修：排程与重规划都改成「先算交通、再定下一个活动」；C5 新增检查 `leg.depart_at >= 上一节点.end_at` 与 `leg.arrive_at <= 下一节点.start_at` |
| 攻略失败仍返回 READY | ✅ 已修：新增 `stage=GUIDE_INCOMPLETE`，计划有效但攻略缺素材时不再谎报 READY |

## 三、你提的 C 线后续问题：处理结果

| 问题 | 处理 |
|---|---|
| 准备提醒查天气传 `destination_id=None` | ✅ 已修：现在带 `destination_id`，准备提醒不会空 |
| `idempotency_key` 未生效 | ✅ 已修：confirm / modify 都按幂等键去重，同一键重复提交返回上次结果、不再升版本 |
| 事件重规划可能动到同日无关节点 | ✅ 已收窄：下雨只换当天**室外**安排；「累了」只动当天**最后一个**景点；闭馆/人流/出发晚**必须指明具体地点**，不再自动整片替换 |

## 四、接下来请你做的（不阻塞演示，P1 节奏）

1. 真实 Provider 替换 `V04MockMCPProvider`（MySQL / Chroma / 实时路线与天气）。
2. `hotel_id` / `lodging_id` → `resource_id` 归一化（Q4 已定，Provider 层做）。
3. `get_weather` 缺日期抛 `DataMissingError` 的口径写进 README。
4. 数据源可行性表（A6）与测试 fixture（A7）。

## 五、边界与注意

- 不要修改 `backend/app/schemas/`、`contracts/`、`fixtures/`；要新字段先提，等三人确认。
- `V04MockMCPProvider` 的类名与 9 个方法签名请保持不变（C 的图直接调它）。
- `mcp[cli]` 已处理成「缺 SDK 自动 skip」，不要再改回强制导入。
- 自查：`python tools/check_a_data.py`（退出码 0 = 全齐）。
