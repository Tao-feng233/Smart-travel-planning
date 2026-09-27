# 给 B 的待办总表（LLM 决策 / Vue 前端）

> 更新时间：2026-09-27 · main = `3a5805c`（C1–C7 已完成，攻略接口已就位）
> 一句话：**后端到攻略的链路全通了，你的 B6/B7 可以直接走 HTTP；先做分支同步，再按新 stage 接页面。**

## 一、必做

1. **先同步分支再推**：你的 `feature/llm-vue` 现在落后 main **六个提交**
   （`c6147e0`、`885dcdd`、`6720d24`、`3a5805c` 等）。
   不先 `git fetch origin && git merge origin/main`，我合你的时候会把 C4–C7 的文件删掉
   （这个坑已经踩过一次）。
2. **前端接口就位了**（`CONTRACTS.md` §13.2，全部统一信封）：

```text
GET  /api/guides/{id}?version=     取攻略（七部分）
POST /api/guides/{id}/confirm      请求 {expected_guide_version, lock_node_ids[], idempotency_key}
                                   → {travel_guide}，lifecycle_status=CONFIRMED，版本 +1
POST /api/guides/{id}/modify       请求 {action: UserAction(MODIFY_GUIDE)}
                                   → {travel_guide, version_lineage, conflicts}
POST /api/guides/{id}/incident     请求 {action: UserAction(REPORT_INCIDENT, raw_text="今天下雨了")}
                                   → {travel_guide, version_lineage, conflicts}
```

3. **新的 stage 要接**：确认目的地后现在是
   `READY`（行程就绪，`data.guide_id` 有值）或 `REPAIRING`（有问题待处理）；
   聊天里说「今天下雨了」「美术馆闭馆了」会直接触发重规划并返回新版本。
4. **错误按信封展示**：404 `DATA_MISSING`（攻略不存在）、409 `VERSION_CONFLICT`（版本过期，要求刷新）、
   409 `DATA_MISSING`（素材缺失，`error.details` 里是缺什么，例如 `LODGING_CANDIDATES`）。
   **组不出攻略时会明确报缺，不会给你半个攻略**——照着 `details` 提示用户找数据方补即可。

## 二、你已经做完、不用再动的

- `request_parser` 用例数已订正为 18（4 处）
- 顶栏模拟数据提示已去重（信封 `MOCK_DATA_IN_DEMO` 前端过滤）
- 「玩 N 天多算一天」的确定性修复（逻辑正确，已复核）
- `backend/app/api/deps.py` 的装配（LLM 优先、无 Key 降级到规则式）

## 三、P0 剩下的前端动作

- B7：把上面四个接口接到页面（攻略七部分已能从后端拿到真实结构，不再靠 fixture）
- 攻略页展示 `version_lineage` 的变化（哪几个节点被替换/保留）与 `conflicts` 提示
- 端到端演示脚本：建会话 → 追问 → 确认 → 取攻略 → 确认攻略 → 报「下雨」→ 看新版本

## 四、等你前端配合决策的两件事（三人拍板前不要动契约）

- **Q6 追问结构化**：现在前端是解析我写的「1. 2. 3.」文本；要么加 `questions` 字段，要么明确文案冻结。
- **Q8 候选卡片 `name`**：要卡片标题显示中文名，需要在 `DestinationRecommendation` 加字段（契约变更）。
  攻略里的目的地名已经带了（`trip_summary.destination_names`），候选卡片暂时可以先用它兜一下。

## 五、不要动的东西

- `backend/app/schemas/`、`contracts/`、`fixtures/`：改字段必须先三人确认
- C 的文件（`services/` 里的规划/验证/修复/攻略、`api/routes.py`、`graph/`）：
  需要新能力就提，别自己改；`request_parser.py` 已归 C 维护
- `tools/check_a_data.py` 是 A 的数据自查脚本，别当成测试删掉
