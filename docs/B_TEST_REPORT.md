# B 线测试报告（LLM 决策 + Vue 前端）

- 报告人：成员 B
- 分支：`feature/llm-vue`
- 测试日期：2026-09-24（**2026-09-27 两轮复核更新：先 merge `origin/main` 复核，后接 C7 攻略接口做 B7**，见下方两个复核提示块）
- 契约基线：`schema-v0.4`（`CONTRACTS.md` / `backend/app/schemas/v04/`）
- 一句话结论：**B 线交付物全部就位，B 线自身 103 个自动化用例全过、7 组 HTTP 端到端全过 + 5 组攻略接口端到端全过、前端类型检查与生产构建全过；过程中发现并修复 12 处问题，其中 3 个是阻断主流程的严重缺陷、5 处是 B 自己此前写错的。**

> **复核提示（2026-09-27，merge `origin/main` 之后）**
>
> 本报告写于 merge 之前。复核时对**每一个可核验数字**重新实测，差异如下。
> **正文数字一律不改**，保留为当日快照，便于对照 —— 只有原清单漏列的
> `src/App.vue` 属于当时就写错，已修正。
>
> | 项 | 本报告（09-24 快照） | 复核实测（09-27） |
> | --- | --- | --- |
> | 全量用例 | 211 passed | **226 passed, 1 skipped** |
> | B 线自身用例 | 99 | **103**（本次新增 4 个「N 天」时长用例） |
> | C/A 线用例 | 112 | 123（A、C 两条线各自推进所致） |
> | `test_request_parser.py` | 18 | 24（C 收尾时补 6 个） |
> | `test_v04_mock_provider.py` | 11 | 16（A 线推进所致） |
> | 前端文件数 | 30 | **31**（原清单漏列 `src/App.vue`） |
> | 报告中的依赖版本 | 8 项 | 逐项实测**完全一致** |
> | B 线四个测试文件用例数 | 29/25/24/13/8 | 逐项实测**完全一致** |
> | HTTP 端到端 | 7 / 7 | 重新实测 **7 / 7 仍然成立** |
>
> 另：复核发现第 7 个缺陷（见第四节），它会让「玩 5 天」这类最自然的口语
> 说法在链路第一步就收到「覆盖不足」—— 属主流程阻断级，已修复并补测。

> **B7 复核实测（2026-09-27，C7 攻略接口就位之后）**
>
> C7 已交付，B6/B5 的 HTTP 出口**不再缺失**，第六节与第七节里「尚未实现 / 无 HTTP 链路」
> 的表述**均已过期**（下方对应行已逐条标注）。本节数字为本轮实测。
>
> | 项 | 复核实测（09-27 B7） |
> | --- | --- |
> | 全量用例 | **292 passed, 1 skipped**（skip = `tests/test_a_mcp_server.py`，本机 venv 未装 `mcp` SDK） |
> | 与 main 的差值来源 | main（`76f0e30`）288 + 本次 B 线新增 4（`test_llm_request_parser.py` 25 → 29）= **292**，已逐文件核实 |
> | 前端 | `vue-tsc --noEmit` 退出码 0；`vite build` 退出码 0 |
> | 攻略接口对接 | ~~四个接口全部接进页面，前端载荷与真实路由**逐字段实测通过**（见 3.5）~~ → **第三轮订正**：四个接口的**客户端**全部就绪，但 `/confirm`、`/incident` 才有页面入口，`/modify` **仅请求层**（`modifyGuide` 已定义、无页面入口，见第六节）。3.5 的 5 组实测覆盖 GET/confirm/incident，**不含 modify** |
> | 端到端演示脚本 | 新增 `tools/check_b_flow.py`，逐步打印 stage，`--deps fake` 全链路跑通 |
>
> 本轮又发现并修掉 5 处问题（第 1、4、5 处是 B 自己此前写错的），见第四节「缺陷 8–12」；
> 另发现 2 处**接口缺口属 C 侧**，已记入 7.1，B 未改 C 的任何文件。

> **第三轮复核（2026-09-27，A / C 两侧 P0 修复之后）**
>
> 前提：`origin/main` 已推进到 `028c89d`（= C 的 `0dc6984` 三缺口修复 + A 的 `fd52aad`
> Mock 覆盖 + 合并 B 分支的 `2f5dda1`）。B 已把 `origin/main` merge 进 `feature/llm-vue`，
> **快进、零冲突**。
>
> | 项 | 本轮实测 |
> | --- | --- |
> | 全量用例 | **302 passed, 1 skipped** |
> | 与上一块 292 的差值来源 | 全部来自 main 侧（C/A 本轮新增），B 本轮未改后端测试 |
> | `tools/check_b_flow.py --deps real` | **退出码 0** —— A 补齐成都 Mock 后**真实数据已能完整跑通**（不再是上一块的 `2`） |
> | 前端 | `vue-tsc --noEmit` 退出码 0；`vite build` 退出码 0（1726 modules） |
> | 新增交付 | `GUIDE_INCOMPLETE` 阶段的前端对接（见下） |
>
> **逐条实测 C 的「三处缺口已全部修复」：**
>
> | # | C 的声明 | 本轮实测 | 结论 |
> | --- | --- | --- | --- |
> | 1 | `?version=` 现在是真参数 | `?version=1/2/3` → 200 且内容各异；`?version=99` → 404 `DATA_MISSING` | **成立** |
> | 2 | `GET /api/sessions/{id}` 现在会返回 `guide_id` | 返回体顶层**没有** `guide_id`，只有 `current_guide_id = "guide_xxxx"` | **不成立**（但 B 不需要它改，见下） |
> | 3 | `/incident` 的谱系带 `parent_guide_version` / `new_guide_version` | 实测 `2 / 3` | **成立** |
>
> 关于声明 2 —— 结论是「**B 不需要 C 再改，但 C 的修法与表述都不准确**」：
>
> 1. `CONTRACTS.md` §13.1 明确规定 `GET /api/sessions/{id}` 的响应就是 **`PlanState`**；
>    §10.2 的 `PlanState` 字段名是 **`current_guide_id`**，**没有 `guide_id`**
>    （`guide_id` 只出现在 §13.1 的 `POST /api/sessions/{id}/messages` 响应里）。
> 2. 因此 C 若真让这个接口多返回一个 `guide_id`，反而是**违约**。
> 3. `current_guide_id` **一直都有值**：实测走完链路后 `GET` 回 `guide_e616989e`
>    —— B 前端真正需要的东西本来就在，只是名字不叫 `guide_id`。
> 4. C 在 `session_service.get_state()` 里补的 `guide_id=extras.current_guide_id` 是传给
>    `build_reply()` 的，而 `api/routes.py` 的 `get_session()` 用
>    `state, _reply, warnings = service.get_state(...)` **把 reply 丢掉了**、直接返回
>    `state.model_dump()` —— 那行改动对本接口是**空操作**（无害，但没打在点上）。
>
> **本轮新增：`GUIDE_INCOMPLETE` 阶段的前端对接**
>
> 待办总表第二节要求「计划有效但攻略缺素材，不要显示成 READY，黄色提示 + 列 `degraded_items`」。
> 实测后端该分支位于 `graph/nodes.py`（组不出攻略时只回 `GUIDE_INCOMPLETE`，刻意不报 READY），
> `reply_builder` 此时会把缺项拼成 `degraded_items`（`攻略暂时组装不了：{note}`）一起返回。
>
> | 改动 | 文件 |
> | --- | --- |
> | 阶段词表补 `GUIDE_INCOMPLETE` / `REPLANNING`（原先缺，会原样显示英文枚举） | `frontend/src/utils/labels.ts` |
> | 阶段标签按语义上色（`GUIDE_INCOMPLETE` 黄 / `INSUFFICIENT_DATA` 红），并加一条**不可关闭**的黄色说明 + 缺失清单 | `frontend/src/components/StatusBanner.vue` |
> | 攻略空态区分「还没生成」与「组装不出来」，后者不再暗示"再等等就好" | `frontend/src/views/GuideView.vue` |
> | 新增本地演示入口「演示攻略不完整」（新阶段在真实数据下触发不到，否则这段代码走不到） | `frontend/src/stores/session.ts`、`src/App.vue` |
> | **修掉 `REPAIRING` 状态下 `conflicts` 完全不可见**（自查发现）：`GuideChangePanel` 原先只挂在「有攻略」的分支里，而首次规划卡在 `REPAIRING` 时**还没有攻略**，后端明明带回了 `conflicts` 却一条都显示不出来 | `frontend/src/components/guide/GuideChangePanel.vue`（`guide` 改可空、标题随内容变）、`frontend/src/views/GuideView.vue`（新增 `hasChangeInfo` 分支） |
> | 顺带把 `repair_options` 的文案列出来（原先只显示"可选修法 N 个"）；只**列出**、不在组件里发起修改 | `frontend/src/components/guide/GuideChangePanel.vue` |
> | **删掉 3 处已过期的注释**（都还在说 `GET /api/guides/{id}?version=N` 返回 404、"`version` 参数是死的"——C 已改为按 `(guide_id, guide_version)` 保留全历史） | `frontend/src/api/guides.ts`、`frontend/src/stores/session.ts`、`frontend/src/components/guide/GuideChangePanel.vue` |
> | 删掉 `guideId` 的 localStorage 绕行（见下方「声明 2」） | `frontend/src/stores/session.ts` |
>
> **本轮新发现（C 侧，建议登记为新 Q）**：`GUIDE_INCOMPLETE` 是**刷新后信息会丢**的阶段
> —— `GET /api/sessions/{id}` 按契约只返回 `PlanState`，而 `PlanState` **没有
> `degraded_items` 字段**，`get_state()` 也没把 `guide_notes` 传进 `build_reply()`。
> 于是刷新页面后阶段还在（`current_guide_id` 之类都在），但「缺什么」的清单必然为空。
> B 的前端如实降级为「后端只标了阶段，没有给出缺失清单」，**没有猜、也没有编**。
> 是否要让该接口带上缺项，属契约变更，需三人评审。


---

## 一、测试环境

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.10.9 | 项目自带 `.venv`（未使用全局环境） |
| langgraph | 1.2.12 | 本次新装，满足 `backend/requirements.txt` 的 `langgraph>=0.2` |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | 本次新装，满足 `pytest>=7.4` / `pytest-asyncio>=0.23` |
| pydantic / fastapi / httpx | 2.13.5 / 0.141.1 / 0.28.1 | 契约与接口运行时 |
| Node / npm | 24.21.0 / 11.19.0 | 前端构建链 |
| Vue / Vite / Element Plus | 3.5 / 6.4 / 2.9 | 前端技术栈（`AGENTS.md` 指定） |
| LLM 通道 | DeepSeek `deepseek-chat` | OpenAI 兼容协议，经 `backend/app/llm/provider.py` 调用 |

---

## 二、验证方法（四层）

| 层次 | 手段 | 覆盖对象 |
| --- | --- | --- |
| L1 单元测试 | 真实 pytest，211 个用例 | 全员代码（B 线 99 个，其余为 C/A 线 112 个） |
| L2 组件级真实调用 | 直连真实 LLM，检查 `used_llm` / `diagnostics` / 输出对象 | B2 需求提取、B4 目的地推荐、B5 意图识别 |
| L3 HTTP 端到端 | 起 uvicorn，真实请求三个会话接口 | 建会话 → 追问 → 补齐 → 推荐 → 改需求 → 错误分支 |
| L4 前端静态与构建 | `vue-tsc --noEmit`、`vite build`、开发服务器逐模块请求 | 前端全部源码 |

> 说明：`/api/guides/...`（C7）与 `UserAction` 路由尚未实现，因此 B6 攻略组装与 B5 意图识别**无法走 HTTP 链路**，采用 L1 + L2 直接调用验证。
>
> **已过期（2026-09-27）**：C7 已交付四个攻略接口，B7 已把 B6 攻略正文与 B5 `UserAction`
> 接到这些接口上，并新增 **L3b 攻略接口端到端**（见 3.5）。本句保留为 09-24 当时的快照。

---

## 三、结果汇总

### 3.1 单元测试：211 passed / 0 failed

| 测试文件 | 用例数 | 归属 |
| --- | --- | --- |
| `test_guide_composer.py` | 29 | B6 攻略组装 |
| `test_llm_request_parser.py` | 25 | B2 需求提取 |
| `test_action_interpreter.py` | 24 | B5 意图识别 |
| `test_llm_destination_recommender.py` | 13 | B4 目的地推荐 |
| `test_llm_provider.py` | 8 | 通道配置（本次新增） |
| `test_request_parser.py` | 18 | C 线规则式解析器（含本次修复） |
| `test_v04_contract_fixtures.py` | 23 | 契约样例一致性（A/C 线） |
| `test_availability_filter.py` | 15 | C 线 |
| `test_trip_profile_draft.py` | 15 | C 线 |
| `test_graph_clarification.py` | 12 | C 线 |
| `test_v04_mock_provider.py` | 11 | A 线 |
| `test_api_sessions.py` | 10 | C 线 REST |
| `test_missing_fields.py` | 8 | C 线 |
| **合计** | **211** | |

### 3.2 组件级真实 LLM 调用（L2）

| 组件 | 用例 | 结果 |
| --- | --- | --- |
| B2 需求提取 | 隐含需求理解（"别太累""老人走不动太多路"） | PASS：`pace=RELAXED`、`mobility_constraints=["老人走不动太多路"]` |
| B2 需求提取 | 越界目的地（"想去三亚"，清单只有成都/乐山/都江堰） | PASS：`destination_requests=[]`，未编造 ID |
| B2 需求提取 | 多轮补充不清空已有信息 | PASS：出发地/日期保留，预算被覆盖为 20000 |
| B2 需求提取 | 兴趣标签规范化 | PASS：`["FOOD"]`（修复前为 `["美食","FOOD"]`） |
| B5 意图识别 | 6 类意图分类 | PASS：REMOVE_NODE / REPLACE_NODE / LOWER_INTENSITY / CHANGE_BUDGET / SELECT_DESTINATION / CONFIRM_GUIDE 全部命中 |
| B5 意图识别 | 节点 ID 越界与缺失 | PASS：`target_node_ids=[]` 且 `confident=False`，向用户追问而不猜 |
| B5 意图识别 | 无年份日期（"10月3号"） | PASS：`date=2026-10-03`（修复前为 `None`） |

### 3.3 HTTP 端到端（L3）：7 / 7 PASS

| # | 用例 | 结果 |
| --- | --- | --- |
| C1 | 一句话完整需求 → 画像 + 目的地候选 | PASS（`stage=AWAITING_DESTINATION_CONFIRMATION`，候选带证据 ID） |
| C2 | 结构化追问卡格式补齐信息 | PASS（`2026-10-02 → 2026-10-06`，预算 5000，弹性 FIXED） |
| C3 | 多轮改需求（版本 1 → 2，旧字段保留） | PASS |
| C4 | 过期版本提交必须 409 | PASS（`VERSION_CONFLICT`） |
| C5 | 越界目的地不编造 | PASS（点名目的地为空，改从覆盖达标集合推荐） |
| C6 | 不存在的会话 | PASS（404 / `DATA_MISSING`） |
| C7 | API Key 不出现在任何响应体 | PASS |

### 3.4 前端（L4）

- `vue-tsc --noEmit`：**通过，0 错误**
- `vite build`：**通过**（1722 modules，8.9s）
- 开发服务器逐模块请求：`main.ts` / `App.vue` / 各组件 / 各工具模块全部 HTTP 200，无转换错误
- fixture 跨目录读取：`/@fs/D:/ProjectB/fixtures/valid/travel_guide.json` 解析正确（未复制样例数据）

### 3.5 攻略接口端到端（L3b，2026-09-27 B7 新增）

用前端**逐字段一模一样**的载荷打真实路由（`TestClient` + 测试替身依赖），验证对接不是"看签名猜的"：

| # | 调用 | 前端载荷要点 | 实测结果 |
| --- | --- | --- | --- |
| 1 | `GET /api/guides/{id}` | 无 | `200`，七部分齐，`guide_version=1`，`lifecycle=DRAFT` |
| 2 | `POST /api/guides/{id}/confirm` | `{expected_guide_version, lock_node_ids:[], idempotency_key}` | `200`，`v1 → v2`，`lifecycle=CONFIRMED` |
| 3 | 同上（重复提交，版本已过期） | 同一 `idempotency_key` + 旧版本号 | `409` `VERSION_CONFLICT`（前端据此改为重新拉取状态） |
| 4 | `POST /api/guides/{id}/incident` | `{action: UserAction(REPORT_INCIDENT, raw_text="今天下雨了")}` | `200`，`v2 → v3`，谱系 6 保留 / 1 替换 / 1 移除 / 1 条替换关系 |
| 5 | 字段集比对 | 前端 TS 声明的字段 vs 实际返回 | `GuideChangeData` 与 `VersionLineage` **完全一致**（无缺无多） |

`tools/check_b_flow.py`（逐步打印 stage，可直接当演示证据）：

| 模式 | 结果 |
| --- | --- |
| `--deps fake`（默认，测试替身） | 退出码 **0**：建会话 → 追问 → 推荐 → 确认 → 七部分攻略 → 确认攻略 → 报突发 → 新版本；`示例历史街区 → 测试室内展馆` |
| `--deps real`（A 的 Mock Provider） | ~~退出码 **2**：第 4 步停在 `INSUFFICIENT_DATA` +「住宿候选数据还没有到位」，**不再是 500**~~ → **第三轮：退出码 0**（A 的 `fd52aad` 补齐 7/7 Mock 覆盖后真实数据已跑通全链路） |

退出码约定：`0` 全通 / `1` 真失败（应报 bug）/ `2` 数据缺口（A 的待办，不是 bug）——
这样它同时是演示材料和 A 的数据探针。

---

## 四、过程中发现并修复的缺陷

| # | 缺陷 | 触发条件 | 影响 | 修复 | 回归用例 |
| --- | --- | --- | --- | --- | --- |
| 1 | **规则式解析器把「返回日期：X」当成出发日期** | 用户回答"哪天回来" | **主流程阻断**：出发日被覆盖，返回日永远缺失，追问无法结束 | `backend/app/services/request_parser.py` 增加标签识别（`出发日期：` / `返回日期：` / `X号回来`），并对"已有出发日时的更晚裸日期"按返回日处理 | `test_request_parser.py` 原有 18 用例全过 |
| 2 | **`provider._REPO_ROOT` 少上溯一层**（算成 `backend/` 而非仓库根） | 配好 Key 后启动 | **严重且静默**：`.env` 读不到 → 通道显示 `disabled` → 调用全部降级到规则式，且不报任何错 | 改为向上查找含 `.env.example` / `.git` 的目录；同时兼容工作目录下的 `.env` | `test_llm_provider.py`（新增 8 用例，含"仓库根必须含 `.env.example`"） |
| 3 | 追问卡文案「希望不要超」命不中 `FIXED` 关键词表 | 用户在卡片里选"不能超" | 预算弹性永远被解析为 `NEGOTIABLE`，与用户意图相反 | 前端文案改为「不能超」 | `test_llm_request_parser.py` Money 相关用例 |
| 4 | 「预算一万」中文数字金额解析不到 | 用户用中文说金额 | 预算字段缺失，多问一轮 | 规则式解析器补 `[中文数字][万/千/百]` 分支 | HTTP C1/C2 实测 |
| 5 | `interests` 中英标签混用（`["美食","FOOD"]`） | 模型返回中文兴趣词 | 下游按标签匹配资源会漏（两套词表并存，语义重复） | `guards.py` 增加标签归一（中文→规范标签，词表外的值原样保留以免丢信息）；提示词同步给出规范词表 | `test_llm_request_parser.py` 新增 3 用例 |
| 6 | B5 "10月3号"这类无年份日期完全丢失 | 用户改行程时不写年份 | 修改意图拿不到目标日期，下游无法定位到具体哪天 | `_extract_date` 支持月日短格式，并按参考日期补年份；`interpret()` 增加可选 `reference_date`（默认今天，向后兼容） | `test_action_interpreter.py` 新增 4 用例 |
| 7 | **「玩 N 天」的返回日期在模型侧摇摆**（2026-09-27 复核发现） | 用户用口语说时长，如「玩5天」 | **主流程阻断**：实测同一句话 6 次里 4 次给出 `出发日+5`（把「含首尾共 5 天」算成 6 天）→ `duration_days=6` → 超过数据层覆盖门槛（成都 12 个游玩地点 < `2×6+1`）→ 第一步即返回「覆盖不足」，推荐与攻略都走不到 | `backend/app/llm/request_parser.py` 在规则辅助中加**显式时长校正**：文本明说「N 天」且用户没写往返两个日期时，以 `start + N - 1` 为准，并记入 `diagnostics` | `test_llm_request_parser.py` 新增 4 用例（含「第一天」不被误读、两个明确日期不被改口） |
| 8 | **前端用 `guide_id` 反推 stage**（B7 自查发现，B 自己此前写错） | 后端在 `REPAIRING`/`PLANNING` 阶段返回响应 | `send()` 里有一句 `if (data.guide_id) stage='READY'`（C7 之前的临时补丁）。实测 `services/reply_builder.py:121-133`：`PLANNING/READY/REPAIRING` 分支带的都是**持久化的上一版** `current_guide_id`，所以 stage 为 `REPAIRING` 时也会带 `guide_id` → 前端把「正在修复冲突」谎报成「攻略已就绪」，并把旧攻略当本轮新产出展示 | `frontend/src/stores/session.ts` 删掉该覆盖，stage 一律只取后端值；`guide_id` 存在但 stage 非 `READY` 时另加一条说明 | `tools/check_b_flow.py` 第 4 步；`build_reply` 四种 stage 逐个实测 |
| 9 | **确认攻略的注释与提示写错了后端语义**（B7 自查发现，B 写错事实） | 点「就按这份走」 | 原注释称"后端从攻略里已有 `locked` 标记的节点取"、提示称"被锁定的节点后续不再自动改动"。实测 `services/session_service.py:227`：`locked = sorted({*lock_node_ids})`，**服务端不会自己挑节点**；传 `[]` 时锁定数为 0，一句都没锁上 | 注释与提示改为如实描述（状态置 `CONFIRMED`、版本 +1、本页暂不支持逐节点锁定），按钮加 tooltip 说明 | 传 `[]` 与传全部节点的两组实测对比 |
| 10 | **谱系里的旧节点名显示成裸 ID**（B7 自查发现，B 漏考虑） | 报突发后看「本轮改动」面板 | `removed_node_ids` 与 `replacement_relations.old_node_id` 是**旧版**节点，在新版正文里查不到名字 → 面板显示 `node_39b89926`。且 `GET /api/guides/{id}?version=N` 取不到历史版本（见 7.1），没法回查 | 新增 `lineageBaseGuide` 保存"改动前那一版"作索引，组件双版查名；两版都查不到时如实标「名称不可得」 | `tools/check_b_flow.py` 第 8 步（校验保留/替换在新版、移除/被替换在旧版，两版合起来全覆盖） |
| 11 | **通用错误文案盖掉后端具体原因**（B7 自查发现，既有代码） | 后端返回 `error.code='DATA_MISSING'` 但 `message` 是具体原因 | `ApiError` 原为 `ERROR_TEXT[code] ?? detail.message`，`DATA_MISSING` 在多个场景复用（攻略不存在 / 素材缺失 / 「本轮没有需要调整的安排」），用户看到的却是「找不到对应的会话或数据」，真实原因被盖掉、没法自救 | `frontend/src/api/client.ts` 改为**后端 `message` 优先**，`ERROR_TEXT` 降为兜底 | `tools/check_b_flow.py` 锁全部节点后报突发（实测返回「2026-10-02 没有需要调整的安排」） |
| 12 | **两个动作按钮同时转圈 / 用残留错误判成败**（B7 自查发现，B 写错） | 攻略页点动作 | ① 两个按钮都绑 `store.loading` → 同时转圈，分不清哪次请求在跑；② 组件用 `store.error` 判成败 → 会把**上一轮**别的操作残留的错误报成"本次失败" | 组件加本地 `pending: 'confirm' \| 'incident' \| null`；`confirmCurrentGuide` / `reportIncidentNow` 改为返回 `boolean`，组件只看返回值 | `vue-tsc --noEmit` + `vite build` |

> 补充说明 1：缺陷 1、4 改动了 `backend/app/services/request_parser.py`（C 线文件）。改动均为**增量修复**，未改动任何函数签名与对外行为，改动后全量用例通过。如需 C 线自行处理，可直接回退该文件的这几处改动。
>
> 补充说明 2：缺陷 6、7 的**规则式解析器侧本来就有正确实现**（`request_parser.py` 的「N 天」分支），问题出在 B 的 LLM 层：`_apply_rule_assist` 的策略是「模型已有值不动、只补空字段」，于是模型多算一天的结果被直接放行。本次修复把「用户明说的时长」提到与规则式同一口径。
>
> 补充说明 3：该缺陷同时暴露一个**跨线口径问题**（建议 C / A 关注）：数据层覆盖门槛 `required = duration_days × 2 + 1` 与 mock 数据规模相互卡得很紧 —— 成都 12 个游玩地点只够撑 5 天行程，6 天即判不可规划。**门槛本身是否该这么陡，建议在 C 侧确认**（见 `PROGRESS_REPORT.md` 第 5 节 `KnowledgeCoverage` 那条「待定」）。
>
> 补充说明 4（2026-09-27 B7）：缺陷 8、9、12 是 **B 自己此前写错**的东西 —— 8 是 C7 之前留下的临时补丁
> 没随接口就位一起删掉，9 是把后端语义写错了，12 是组件层的两处误用。三条都不是"改需求"，
> 而是"前后端说法不一致"：**前端替后端下结论、注释与实现不符**。这也是本轮把
> `tools/check_b_flow.py` 做出来的原因 —— 逐步打印 stage，让"前端显示的"和"后端返回的"直接并排可见。
> 缺陷 10、11 中，10 是 B 漏考虑（旧节点名解析），11 是既有代码的通用文案盖掉具体原因。

---

## 五、契约与红线符合性核对

| 红线（`AGENTS.md` / `CONTRACTS.md`） | 核对方式 | 结果 |
| --- | --- | --- |
| 不修改 `CONTRACTS.md` 与 `backend/app/schemas/` | `git status` 检查 | 符合（两者均无改动） |
| 不修改 `contracts/` 与 `fixtures/` 样例 | `git status` 检查 | 符合 |
| LLM 不是旅游事实来源 | B2/B4 护栏：事实性断言与命中事实关键词的推荐理由整条丢弃 | 符合（组件级实测） |
| 只推荐 `planning_ready=true` 的目的地 | HTTP C5 实测 | 符合 |
| LLM 只能返回候选集合内已存在的实体 ID | 越界 ID 丢弃并记诊断；未提供候选清单时全部丢弃 | 符合（B2/B4/B5 三处均有覆盖） |
| 缺失对象发 `SCHEMA_BLOCKER`、不用 `dict` 顶替 | 实现中未出现 `dict` 顶替 | 符合 |
| `PlanNode/DayPlan`（内部）与 `GuideNode/GuideDay`（展示）不混用 | `test_guide_composer.py` 专项用例（内部字段不泄漏到展示对象） | 符合 |
| 普通交通只用 `TravelLeg`，不建 `TRANSFER` 节点 | B6 组装未产生 TRANSFER 节点 | 符合 |
| 预算只能由 `CostItem[]` 复算 | 前端仅展示后端 `BudgetSummary`，不做任何加减；B6 的 `estimated_cost` 逐项求和 | 符合 |
| `Money` 的 `amount` 与 `min/max` 互斥且必有一方 | 归一化处理三种非法形状（只有 min / 只有 max / 区间反转），均有用例 | 符合 |
| 计划可行性 / 数据可信度 / 攻略生命周期三状态分离 | B6 合成 `guide_readiness` 的输出与官方 fixture 完全一致；前端三状态并行展示 | 符合 |
| 所有 LLM 失败降级到规则式并在 `diagnostics` 写明原因，绝不静默 | 降级路径 3 类（未配置 / 通道异常 / 输出不合法）各有用例 | 符合 |
| Key 只走环境变量，前端不持有任何服务端 Key | `.env` 被 gitignore（`git status` 未出现）；前端仅 `VITE_API_BASE_URL` 与演示开关 | 符合 |

---

## 六、覆盖不到的部分与遗留风险

| 项 | 说明 | 影响 |
| --- | --- | --- |
| ~~B6 攻略组装无 HTTP 链路~~ **已解除（2026-09-27 B7）** | `/api/guides/...`（C7）已交付，B7 已接进页面 | 已与真实规划产物对接过：见 3.5 的 5 组攻略接口端到端；不再依赖 fixture |
| ~~B5 无 HTTP 链路~~ **已解除（2026-09-27 B7）** | `UserAction` 路由（`/modify`、`/incident`）已实现 | 先接的是 `REPORT_INCIDENT`（页面「上报突发」）；`MODIFY_GUIDE` 的请求层已就绪（`api/guides.ts` 的 `modifyGuide`），**尚无页面入口** |
| ~~端到端止于"目的地确认"~~ **已解除（2026-09-27）** | C4/C5/C6/C7 全部交付 | 全链路已跑通：`tools/check_b_flow.py --deps fake` 到「报突发 → 新版本」，退出码 0。~~真实数据下仍止于 `INSUFFICIENT_DATA`（A 缺住宿等 6 项，非代码问题）~~ → **第三轮已解除：A 补齐后 `--deps real` 退出码 0** |
| 组装规则出自 fixture 反推 | 非 C 线当面确认的口径 | 建议 C 线复核 `compose_travel_guide()` 的富化与求和规则（B7 之后已有真实链路产物可比对） |
| `DestinationRecommendation` 缺 `name` 字段 | 前端候选卡片只能显示 `dest_chengdu` 这类 ID | 建议提给全员，由 C 线加字段（前端已就绪，加字段后无需改动）；属 Q8 |
| 浏览器自动化验证未完成 | agent-browser 守护进程在本机反复挂起（已成功打开页面一次，标题正确） | 前端渲染以人工查看 + 静态检查替代，不影响功能（B7 新增的改动面板同此口径） |
| 前端会话持久化仅存"钥匙" | 只持久化 `sessionId`、`runMode`、消息与画像版本号；**攻略 ID 不再单独存**，直接从刷新状态里的 `current_guide_id` 读 | 后端为内存存储，重启后旧会话失效时静默新建（已处理）。~~`guideId` 是 B7 新增的钥匙，理由见 7.1 第 2 条~~ → **第三轮已删**：那不是接口缺口，是 B 找错了字段名（详见第三轮复核块）；顺带去掉了一次多余的 `refreshState()` 重复请求 |
| ~~**真实数据下跑不到 `READY`**（2026-09-27 新增）~~ **已解除（第三轮）** | ~~A 的必修数据 7 项里 6 项未到位（住宿候选/住宿区域/景点间路线/返程城际/天气覆盖/车站-住宿路线）~~ | 决定"能不能演示完整行程"的曾是 **A 的数据**。A 的 `fd52aad` 补齐 7/7 后，`tools/check_b_flow.py --deps real` 已 **退出码 0**（第 4 步拿到 `guide_id`，一路到「报突发 → 新版本」）。演示不再必须用 `--deps fake` |
| **`GUIDE_INCOMPLETE` 缺后端测试覆盖**（第三轮新发现） | `backend/tests/` 里搜不到 `GUIDE_INCOMPLETE`，C 的新阶段**没有自动化用例** | B 无法替 C 补（属 `graph/` 与测试）。前端已按契约渲染该阶段，但**B 不做"已验收"声明** —— 见 7.1 新增行 |
| **`REPAIRING + conflicts[]` 未在 HTTP 层实测**（2026-09-27 新增） | 该分支要求"有计划但修不动"；C 的 `test_repair_loop_is_bounded` 锁的是**路由**判定而非 HTTP 响应 | **第三轮多次尝试仍无法到达**（真实数据全程 READY；把 17 个节点全锁后用聊天报突发，落到 `INSUFFICIENT_DATA` 而非 `REPAIRING`；走 `/incident` 接口则返回 `409 DATA_MISSING`）。**但 B 修掉了这个状态下的一处真缺漏**：`conflicts` 原先只挂在「有攻略」下面，首次规划卡在 `REPAIRING` 时**一条都显示不出来**（那时 `guide_id` 为空）；现已改为「有计划但没攻略」也要露出，并把 `repair_options` 的文案列出来。**仍不做"已验收"声明** |
| **`INSUFFICIENT_DATA` 可能一条原因都不给**（第三轮顺带实测到，窄路径） | 触发条件：`confirm` 时把**全部节点**锁定（`lock_node_ids` 传全量 17 个），再用聊天报「今天下雨了」 | 实测返回 `stage=INSUFFICIENT_DATA`、`conflicts=[]`、**`degraded_items=[]`**，`assistant_message` 只有通用文案 —— 用户拿不到任何"缺什么"的线索。对照：正常路径（不锁节点）报同样的话会正常走到 `READY` v2。**该状态只能由手工调 API 造出**（前端 `confirm` 传的是 `lock_node_ids: []`），故不影响页面；但 `INSUFFICIENT_DATA` 不带原因这条口径值得 C 看一眼 |

---

## 七、给 A / C 的对接说明

本节收拢 B 线**无法单方完成、需要对方提供前置**的事项。
所有接口路径照 `CONTRACTS.md` §13 原文引用，未自行命名。

### 7.1 需要 C 提供

| 事项 | 卡住什么 | B 侧现状 |
| --- | --- | --- |
| ~~`GET /api/guides/{id}?version=`（§13.2）~~ **已交付（C7）** | 已不卡 | B7 已接入并实测通过（3.5 第 1 组） |
| ~~`POST /api/guides/{id}/modify`、`/incident`（§13.2）~~ **已交付（C7）** | 已不卡 | `REPORT_INCIDENT` 已接进页面；`MODIFY_GUIDE` 请求层就绪、尚无页面入口 |
| ~~C3–C6 规划链路~~ **已交付** | 已不卡 | 全链路已跑通（`tools/check_b_flow.py`） |
| 复核 `compose_travel_guide()` 的富化与求和规则 | 该规则由官方 fixture 反推，非当面确认口径 | 若与 C4/C5 口径不符，改动集中在 `backend/app/guide/composer.py` 单文件 |
| `DestinationRecommendation` 补 `name` 字段 | 前端候选卡片只能显示 `dest_chengdu` 这类 ID | 前端已就绪，后端加字段后前端无需改动（属 Q8） |
| 复核 B 对 `request_parser.py` 的修正 | 修的是「返回日期被当成出发日期，导致追问关不上」 | 改动最小化，该文件原有用例全过 |
| 复核 B 本次新增的「显式时长校正」（2026-09-27 新增） | 该规则**会覆盖模型给出的返回日期**（仅在用户没写往返两个日期时生效） | 改动集中在 `backend/app/llm/request_parser.py` 单文件，4 个专项用例覆盖（含不介入的边界） |
| **确认覆盖门槛 `duration_days × 2 + 1` 是否过陡**（2026-09-27 新增） | 成都 12 个游玩地点**只够撑 5 天**：门槛 11 勉强过、13 就不过。口语说「玩 5 天」一旦被算成 6 天，链路第一步就断 | B 已在解析层修掉「多算一天」（缺陷 7），但**门槛与 mock 数据规模的匹配关系需要 C / A 定夺**（Q9） |
| **`GUIDE_INCOMPLETE` 无自动化用例**（第三轮新发现） | 这个阶段只在「计划已验证通过、但攻略组装缺素材」时出现，**没有任何测试锁住它**；也没有可复现的触发入口 | B 实测：`backend/tests/` 内 `grep GUIDE_INCOMPLETE` **零命中**。B 无法替 C 补（属 `graph/` 与测试文件）。前端已按契约渲染（见第三轮复核块），但因**无法在真实数据上触发**，B 只能给一个本地演示入口，**不做"已验收"声明** |
| **是否给 `GET /api/sessions/{id}` 带上 `degraded_items`**（第三轮新发现，建议登记为新 Q） | `GUIDE_INCOMPLETE` 刷新后缺项清单丢失，前端只能显示「没有给出缺失清单」 | 契约 §13.1 该接口只返回 `PlanState`，而 `PlanState` 无 `degraded_items`。**改契约需三人评审**，B 未擅自扩展；前端已按"取不到就如实说取不到"的方式降级 |
| ~~**`GET /api/guides/{id}?version=N` 取不到历史版本**（2026-09-27 B7 实测发现）~~ **已修复（C `0dc6984`；第三轮实测 `?version=1/2/3` → 200、`?version=99` → 404 `DATA_MISSING`）** | 谱系（`version_lineage`）里 `removed_node_ids` 与 `replacement_relations.old_node_id` 是**旧版**节点，前端想回查旧版正文取名字却拿不到 | 原实测：`v2.parent_guide_version=1`（有值），但 `GET /api/guides/{id}?version=1` → **404 `DATA_MISSING`**。根因是 `services/guide_service.py` 的 `store_guide()` 按 `guide_id` 覆盖，同一 `guide_id` 只留最新版。**已在 `0dc6984` 改为按 `(guide_id, guide_version)` 保留全历史**。B 的前端仍保留"改动前那一版"作本地索引（缺陷 10），两版互补、不冲突 |
| ~~**`GET /api/sessions/{id}` 从不返回 `guide_id`**（2026-09-27 B7 实测发现）~~ **已澄清：B 不需要 C 再改（第三轮）** | 前端刷新页面后拿不到攻略 ID，页面会从「有攻略」退回「攻略还没有生成」 | 第三轮澄清后**结论反转**：契约 §13.1 规定该接口响应是 **`PlanState`**，§10.2 的 `PlanState` 字段名是 **`current_guide_id`**、**没有 `guide_id`**；`guide_id` 只在 §13.1 的 `POST .../messages` 响应里。实测 `current_guide_id` **一直有值**（`guide_e616989e`），B 需要的东西本来就在。C 在 `0dc6984` 补的 `get_state()` 传参对象是 `build_reply()`，而 `routes.py` 的 `get_session()` 把 reply 丢弃、只返回 `state.model_dump()` —— 那行改动对本接口是**空操作**。**故不再作为待办；B 前端改为直接读 `current_guide_id`** |
| ~~**`/incident` 返回的谱系里攻略版本号恒为 `null`**（2026-09-27 B7 实测发现）~~ **已修复（C `0dc6984`；第三轮实测 `parent=2 / new=3`）** | 前端没法显示「攻略 v2 → v3」，只能显示计划版本变化 | 原实测：`parent_guide_version` / `new_guide_version` **都是 `null`**，而同一响应里 `travel_guide.guide_version` 正常递增（2 → 3）。C 已在 `0dc6984` 的 `_apply_action` 里补值，B 的面板现在能正常显示「v2 → v3」 |
| **`GUIDE_INCOMPLETE` 的缺项清单刷新后会丢**（第三轮新发现，建议登记为新 Q；Q 编号由 C 分配） | 用户刷新页面后，阶段还在（`stage=GUIDE_INCOMPLETE`），但「缺哪些素材」的清单空了 | 契约 §13.1 规定 `GET /api/sessions/{id}` 只返回 `PlanState`，而 `PlanState` **没有 `degraded_items` 字段**；`get_state()` 也未把 `guide_notes` 传给 `build_reply()`（且该 route 会丢弃 reply）。于是缺项清单**必然为空**。B 的前端如实显示「后端只标了阶段，没有给出缺失清单」，**不猜不编**。是否扩展该接口属契约变更，需三人评审 |

### 7.2 需要 A 提供

| 事项 | 卡住什么 | B 侧现状 |
| --- | --- | --- |
| 真实 Provider 替换 `V04MockMCPProvider` | 当前候选与证据均来自 Mock | B 只消费 `ResourceCandidate` 与 `Evidence`，不依赖 Provider 具体实现 |
| 外部数据 `hotel_id` / `lodging_id` 归一化为 `resource_id` | 未归一会导致 B2 的候选 ID 校验把资源整条丢弃 | 已按 Q4 结论实现，**未加兼容分支**（避免同时持有两套 ID 语义） |

### 7.3 B 已守住的三条线（供 A / C 核对）

- **没有绕过 MCP 工具取数**：事实性内容只来自工具返回值或证据；LLM 输出中命中事实关键词的推荐理由整条丢弃。
- **没有新增契约字段**：`CONTRACTS.md`、`backend/app/schemas/`、`contracts/`、`fixtures/` 均无改动（`git status` 可核）。
- **没有持有服务端 Key**：前端只用 `VITE_API_BASE_URL` 与演示开关；Key 仅存于后端 `.env`（已被 `.gitignore` 拦截）。

---

## 八、复现方式

```bash
# 后端：装依赖 → 跑全量测试 → 起服务
cd /d/ProjectB/backend
/d/ProjectB/.venv/Scripts/python.exe -m pytest tests -q
/d/ProjectB/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端：类型检查 → 构建 → 开发服务器
cd /d/ProjectB/frontend
npm install          # 首次
npx vue-tsc --noEmit
npx vite build
npx vite             # http://localhost:5173
```

```bash
# B 线 P0 链路演示（逐步打印 stage，可直接当演示证据；在仓库根目录跑）
python tools/check_b_flow.py                 # 测试替身 → 跑到"报突发 → 新版本"，退出码 0
python tools/check_b_flow.py --deps real     # A 的 Mock Provider → 停在 INSUFFICIENT_DATA，退出码 2
python tools/check_b_flow.py --show-json     # 额外打印每一步的关键 JSON
```

> 退出码：`0` 全通 / `1` 真失败（应报 bug）/ `2` 数据缺口（A 的待办）。
> **真实数据下现在只能得到 2** —— 这不是代码问题，是 A 的住宿等 6 项数据未到位。

配置 LLM 通道：把仓库根 `.env.example` 复制为 `.env`，填 `LLM_PRIMARY_API_KEY` / `BASE_URL` / `MODEL`。未填写时自动降级到规则式实现，功能可用但语义理解能力受限。

---

## 九、本次变更文件清单（B 线）

**后端新增**
- `backend/app/llm/`：`provider.py`、`guards.py`、`prompts.py`、`contract_hint.py`、`request_parser.py`、`destination_recommender.py`、`action_interpreter.py`、`__init__.py`
- `backend/app/guide/`：`composer.py`、`__init__.py`

**后端修改**
- `backend/app/api/deps.py`（换装配，B 线唯一允许修改的共享文件）
- `backend/app/services/request_parser.py`（C 线文件，本次修复缺陷 1 / 4）

**测试新增**
- `backend/tests/b_line_fakes.py`、`test_llm_request_parser.py`、`test_llm_destination_recommender.py`、`test_action_interpreter.py`、`test_guide_composer.py`、`test_llm_provider.py`

**前端新增（31 个文件）**
- 工程配置（7）：`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig.json`、`env.d.ts`、`index.html`、`.env.example`
- 入口与页面（5）：`src/main.ts`、`src/App.vue`、`src/router/index.ts`、`src/views/{GuideView,StateView}.vue`、`src/styles/main.css`
- 数据层（4）：`src/types/contract.ts`、`src/api/client.ts`、`src/api/sessions.ts`、`src/stores/session.ts`
- 工具层（4）：`src/utils/{format,labels,clarification,fixtureLoader}.ts`
- 组件（11）：`src/components/{StatusBanner,ChatPanel,ClarificationCard}.vue` + `src/components/guide/` 七个分节

> 复核订正（2026-09-27）：原文写 30 个且清单漏列 `src/App.vue`，
> 按 `git ls-files frontend` 实测为 **31 个**（含 `package-lock.json`）。

**B7 变更文件（2026-09-27，C7 攻略接口就位之后）**

| 文件 | 类型 | 改了什么 |
| --- | --- | --- |
| `frontend/src/api/guides.ts` | 新增 | §13.2 的四个接口客户端（`getGuide` / `confirmGuide` / `modifyGuide` / `reportIncident`）。`modifyGuide` 暂无页面入口，保留是为了整组签完契约 |
| `frontend/src/components/guide/GuideChangePanel.vue` | 新增 | 「本轮改动」面板：谱系的保留/替换/移除节点 + 替换关系 + `conflicts`；双版查节点名 |
| `frontend/src/stores/session.ts` | 修改 | `syncGuide` 改走真实接口；新增 `confirmCurrentGuide` / `reportIncidentNow` / `versionLineage` / `lineageBaseGuide`；持久化 `guideId`；删掉 `guide_id → stage='READY'` 的覆盖 |
| `frontend/src/views/GuideView.vue` | 修改 | 挂载改动面板；新增「就按这份走」「上报突发」两个动作；本地 `pending` 区分按钮 loading |
| `frontend/src/types/contract.ts` | 修改 | 补 `UserAction` / `VersionLineage` / `ChangeType` / `ScopeHint` / `ActionChangePayload` / `GuideChangeData` 等类型（照 `app/schemas/v04/` 原样抄，未新增字段） |
| `frontend/src/api/client.ts` | 修改 | `ApiError` 改为后端 `message` 优先，`ERROR_TEXT` 降为兜底 |
| `frontend/src/utils/labels.ts` | 修改 | 补 `CHANGE_NOTE` 的中文标题 |
| `tools/check_b_flow.py` | 新增 | P0 链路演示脚本（逐步打印 stage，退出码三分） |

**文档**

- 新增 `docs/B_TEST_REPORT.md`（本报告，含第 7 节「给 A / C 的对接说明」）
- 修改 `PROGRESS_REPORT.md`（B 行状态、B 线交付记录、第 9 节状态记录——均为追加式，未删改他人内容）
