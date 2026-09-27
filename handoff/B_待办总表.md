# 给 B 的待办总表（LLM 决策 / Vue 前端）

> 更新时间：2026-09-27 · 一句话：**四个攻略接口 + 真实数据现在能完整跑通，按下面口径对接即可。**

## 一、接口（统一信封，`CONTRACTS.md` §13.2）

```text
GET  /api/guides/{id}?version=     取攻略；指定版本可回查历史版本（200）
POST /api/guides/{id}/confirm      请求 {expected_guide_version, lock_node_ids[], idempotency_key}
                                   → {travel_guide}，lifecycle_status=CONFIRMED，版本 +1
                                   同一 idempotency_key 重复提交：返回上次结果，不再升版本
POST /api/guides/{id}/modify       请求 {action: UserAction(MODIFY_GUIDE)}（可选 idempotency_key）
POST /api/guides/{id}/incident     请求 {action: UserAction(REPORT_INCIDENT, raw_text="今天下雨了")}
                                   → {travel_guide, version_lineage, conflicts}
```

`version_lineage` 现在带 `parent_guide_version` / `new_guide_version`，可直接显示「攻略 v2 → v3」。

## 二、stage 取值（两个要接的新增项）

```text
READY             计划已验证 + 攻略已组装（data.guide_id 有值）
GUIDE_INCOMPLETE  计划有效但攻略缺素材（不要显示成 READY，建议黄色提示 + 列 degraded_items）
REPAIRING         计划有问题待处理（conflicts 带严重度/范围/修复选项）
PLANNING / VALIDATING / REPLANNING  中间态，加载提示即可
```

## 三、错误口径

| HTTP | code | 场景 |
|---|---|---|
| 404 | `DATA_MISSING` | 攻略不存在 |
| 409 | `VERSION_CONFLICT` | 版本过期，提示刷新后重试 |
| 409 | `DATA_MISSING` | 素材缺失，`error.details` 说明缺什么 |

组不出攻略时后端明确报缺，不会给半个攻略；此时计划本身仍然有效。

## 四、你报的三处缺口：已全部修复

1. `?version=N` 能取历史版本（按 `(guide_id, guide_version)` 保留全部版本）。
2. `GET /api/sessions/{id}` 返回 `guide_id`（刷新页面不用再靠 localStorage）。
3. `/incident` 的 `version_lineage` 补齐攻略版本号。

## 五、联调命令

```powershell
python tools/check_b_flow.py                 # 测试替身，完整演到"报突发 → 新版本"
python tools/check_b_flow.py --deps real     # 真实 Mock 数据，退出码 0
cd backend && python -m pytest               # 基线：302 passed, 1 skipped
```

## 六、等三人拍板（拍板前不要动契约）

- **Q6 追问结构化**：现在解析 C 写的「1. 2. 3.」文本；要么加 `questions` 字段，要么明确文案冻结。
- **Q8 候选卡片 `name`**：要中文标题需给 `DestinationRecommendation` 加字段；攻略里已有 `trip_summary.destination_names` 可先兜。
- **Q9 覆盖门槛**：`duration_days × 2 + 1` 是否过陡（C 已核出 `visit_place_count` 是硬编码常量）。

## 七、不要动

- `backend/app/schemas/`、`contracts/`、`fixtures/`：改字段先三人确认
- C 的文件（`services/` 规划/验证/修复/攻略、`api/routes.py`、`graph/`）
- `tools/check_a_data.py` / `tools/check_b_flow.py`：联调自查脚本，别删

## 八、2026-09-27 追加：你报的两条 + Q8 已上线

**Q8 已上线**：`DestinationRecommendation` 加了可选 `name`（契约 §6 已更新），
后端在 `reply_builder` 统一用目的地中文名填充，候选卡片可以直接显示中文，
缺失时回退 `destination_id`。你按"优先 name"接即可，A 零工作量。

**你的两条新发现，处理结果**：

1. 刷新后缺项清单会丢 → **不新增契约字段**：`GUIDE_INCOMPLETE` 时的缺项改为通过
   `GET /api/sessions/{id}` 信封的 `warnings` 回带，`code = GUIDE_MATERIAL_MISSING`，
   `message` 就是缺什么。前端刷新后读 warnings 即可还原提示。
2. `GUIDE_INCOMPLETE` 零覆盖 → 已补自动化用例
   （`test_guide_incomplete_stage_and_warning`：stage + guide_id 为空 + 缺项警告）。

**关于 `current_guide_id`**：你说得对——`GET /api/sessions/{id}` 按 §13.1 返回 PlanState，
字段名是 `current_guide_id`（没有 `guide_id`）。我此前那条"补传 guide_id"对该接口是空操作，
而且配套测试是死代码。现在测试改成断言 `current_guide_id` 并真正接入，
你不需要为这个接口做任何改动。
