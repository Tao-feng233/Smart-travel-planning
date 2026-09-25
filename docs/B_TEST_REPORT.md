# B 线测试报告（LLM 决策 + Vue 前端）

- 报告人：成员 B
- 分支：`feature/llm-vue`
- 测试日期：2026-09-24
- 契约基线：`schema-v0.4`（`CONTRACTS.md` / `backend/app/schemas/v04/`）
- 一句话结论：**B 线交付物全部就位，211 个自动化用例全过、7 组 HTTP 端到端全过、前端类型检查与生产构建全过；过程中发现并修复 6 个缺陷，其中 2 个是阻断主流程的严重缺陷。**

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

> 补充说明：缺陷 1、4 改动了 `backend/app/services/request_parser.py`（C 线文件）。改动均为**增量修复**，未改动任何函数签名与对外行为，改动后全量 211 用例通过。如需 C 线自行处理，可直接回退该文件的这几处改动。

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
| B6 攻略组装无 HTTP 链路 | `/api/guides/...`（C7）未实现，只能用官方 fixture 验证 | 组装逻辑与 fixture 完全对齐，但**未与真实规划产物对接过** |
| B5 无 HTTP 链路 | `UserAction` 路由未实现（C7） | 解析器已就绪，接口签名已按契约对齐，待 C 提供路由即可接入 |
| 端到端止于"目的地确认" | C3–C6（抓取资源 → 排程 → 验证）尚未实现 | 完整链路（生成攻略）暂时跑不到，B6 的输入依赖 C 线规划产物 |
| 组装规则出自 fixture 反推 | 非 C 线当面确认的口径 | 建议 C 线复核 `compose_travel_guide()` 的富化与求和规则 |
| `DestinationRecommendation` 缺 `name` 字段 | 前端候选卡片只能显示 `dest_chengdu` 这类 ID | 建议提给全员，由 C 线加字段（前端已就绪，加字段后无需改动） |
| 浏览器自动化验证未完成 | agent-browser 守护进程在本机反复挂起（已成功打开页面一次，标题正确） | 前端渲染以人工查看 + 静态检查替代，不影响功能 |
| 前端会话持久化仅存"钥匙" | 只持久化 `sessionId` 与消息，权威状态仍从后端拉取 | 后端为内存存储，重启后旧会话失效时静默新建（已处理） |

---

## 七、给 A / C 的对接说明

本节收拢 B 线**无法单方完成、需要对方提供前置**的事项。
所有接口路径照 `CONTRACTS.md` §13 原文引用，未自行命名。

### 7.1 需要 C 提供

| 事项 | 卡住什么 | B 侧现状 |
| --- | --- | --- |
| `GET /api/guides/{id}?version=`（§13.2） | B6 七部分组装无 HTTP 出口，只能对 fixture 验证 | `compose_travel_guide()` 已实现，29 个用例全过，接口就位即可接入 |
| `POST /api/guides/{id}/modify`、`POST /api/guides/{id}/incident`（§13.2） | B5 `UserAction`（`MODIFY_GUIDE` / `REPORT_INCIDENT`）无出口 | `ActionInterpreter` 已就绪，签名已按契约对齐 |
| C3–C6 规划链路 | 端到端止于「目的地确认」，跑不到攻略生成 | 组装输入依赖 C 线的 `ItineraryPlan` 产物 |
| 复核 `compose_travel_guide()` 的富化与求和规则 | 该规则由官方 fixture 反推，非当面确认口径 | 若与 C4/C5 口径不符，改动集中在 `backend/app/guide/composer.py` 单文件 |
| `DestinationRecommendation` 补 `name` 字段 | 前端候选卡片只能显示 `dest_chengdu` 这类 ID | 前端已就绪，后端加字段后前端无需改动 |
| 复核 B 对 `request_parser.py` 的修正 | 修的是「返回日期被当成出发日期，导致追问关不上」 | 改动最小化，该文件原有 196 个用例全过 |

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

**前端新增（30 个文件）**
- 工程配置：`package.json`、`vite.config.ts`、`tsconfig.json`、`env.d.ts`、`index.html`、`.env.example`
- 数据层：`src/types/contract.ts`、`src/api/client.ts`、`src/api/sessions.ts`、`src/stores/session.ts`
- 工具层：`src/utils/{format,labels,clarification,fixtureLoader}.ts`
- 组件：`src/components/{StatusBanner,ChatPanel,ClarificationCard}.vue` + `src/components/guide/` 七个分节
- 页面：`src/views/{GuideView,StateView}.vue`、`src/router/index.ts`、`src/main.ts`、`src/styles/main.css`

**文档**

- 新增 `docs/B_TEST_REPORT.md`（本报告，含第 7 节「给 A / C 的对接说明」）
- 修改 `PROGRESS_REPORT.md`（B 行状态、B 线交付记录、第 9 节状态记录——均为追加式，未删改他人内容）
