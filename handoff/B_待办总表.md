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
