# backend —— 后端开发说明

> 三条开发线的共享进度台账见仓库根目录的 `PROGRESS_REPORT.md`；
> 契约待确认项见 `docs/contract-open-questions.md`。

## 当前状态（步骤 10 完成）

已实现共享契约对象（v0.4，旧 v0.3 已删除）、LangGraph 追问/推荐回路、
**C3 前置过滤**、**C4 行程生成（确认目的地 → 排行程 + 费用预算）**、
**C5 计划验证器（10 类检查 + 修复选项 → READY / REPAIRING）**、
**C6 修复引擎（闭馆替换 / 超预算换住宿 / 下雨只重排当天 + VersionLineage）**
、**C7 攻略接口（`/api/guides/...` 四个 + 七部分攻略组装）**
和会话 REST 接口（统一响应信封）。

```text
backend/
├── app/
│   ├── api/           REST 路由与依赖注入（会话接口已完成）
│   ├── core/          运行期配置
│   ├── graph/         LangGraph 阶段、状态节点与工作流（C2 + C3 + C4）
│   ├── schemas/       共享契约对象 v0.4（唯一来源）
│   │   └── v04/       基线模型 / MCP 工具 / REST / 状态
│   ├── providers/     A线统一Provider协议与工厂
│   ├── mcp_server/    A线九工具强类型MCP Server
│   ├── main.py        FastAPI 应用入口
│   └── services/      缺失字段判定、提取、推荐、前置过滤、行程生成、计划验证、
│                      修复引擎、Mock Provider、会话存储
├── tests/
│   └── ...            299 个用例（装齐 requirements；未装 MCP SDK 时 298 passed, 1 skipped）
└── requirements.txt
```

契约测试数据在**仓库根目录**的 `fixtures/`（三条线共用），
自检脚本是 `python contracts/validate_fixtures.py`。
A 线数据缺口自查：`python tools/check_a_data.py`（退出码 1 = 还有必修数据没到位）。

## 环境

```powershell
cd backend
python -m pip install -r requirements.txt
```

本项目开发环境已验证：Python 3.12.7、pydantic 2.13.5、fastapi 0.141.1、
langgraph 1.2.11、uvicorn 0.53.0、pytest 7.4.4。

## 运行 API

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 可以直接试接口。

```text
POST /api/sessions                  创建会话
POST /api/sessions/{id}/messages    输入自然语言，推进 LangGraph
GET  /api/sessions/{id}             获取当前 PlanState
GET  /api/guides/{id}?version=      取攻略（七部分）
POST /api/guides/{id}/confirm       确认攻略（锁定节点）
POST /api/guides/{id}/modify        用户修改（P0：换资源 / 删节点）
POST /api/guides/{id}/incident      突发事件重规划（例如「今天下雨了」）
GET  /health                        健康检查
```

响应统一为信封，`data` 里才是业务对象：

```json
{"ok": true, "data": {...}, "warnings": [], "error": null, "trace_id": "trace_xxx"}
```

`POST /api/sessions` 的请求体必须带 `run_mode`（`DEMO` / `VERIFIED`）。

典型两轮对话：

```text
第 1 轮「我想出去玩，不想早起」        → 追问出发地/日期/人数/预算
第 2 轮「从上海出发，10月...2个人，预算5000元」 → 推荐候选 + 证据
第 2 轮（点名目的地）「…，想去成都」    → 推荐候选 + 前置过滤结果（已排除闭馆资源）
```

## 运行测试

```powershell
cd backend
python -m pytest
```

当前结果：安装完整 requirements 时 `299 passed`；未安装可选 MCP SDK 时
对应的 MCP 冒烟测试会自动跳过，不会在测试收集阶段中断。根目录契约校验为
7 个合法、7 个非法、3 个业务用例通过。

测试必须从 `backend` 目录运行；直接在仓库根目录运行时，Python 不会自动把
`backend` 加入模块搜索路径。

### A 线 Mock 数据边界

- 当前成都演示数据覆盖 2026-10-02 至 2026-10-06，包括 11 个游玩地点、
  2 个住宿区域、4 个住宿候选、双向本地路线、去返程城际交通和 5 天天气。
- `get_weather` 请求范围内缺少任意一天时会抛出 `DataMissingError`；该异常继承
  `RuntimeError`，调用方必须明确降级或报告缺失日期，不能把不完整天气当作完整结果。
- 住宿价格、路线耗时、开放信息、天气等均为 `MOCK` / `ESTIMATED` 演示数据，
  不表示实时库存或真实可预订状态。

### 高德实时路线混合模式（`DATA_MODE=HYBRID`）

默认 `DATA_MODE=MOCK` 行为不变：9 个工具全部返回 Mock 数据。
设置 `DATA_MODE=HYBRID` 后：

- `get_route` 优先调用高德 Web 服务「路径规划 2.0」：短距离走
  `/v5/direction/walking`，较远距离走 `/v5/direction/transit/integrated`
  （可含地铁，带成都城市参数；有 `depart_at` 时传日期和时间）。
  成功返回的路线 `source=PLATFORM`、`is_estimated=true`（时长仍是预测值），
  并做确定性排序让规划器取第一条即主方案。
- 其余 8 个工具（景点、住宿、餐厅、天气、城际交通、准备规则等）仍由
  `V04MockMCPProvider` 提供，签名不变。
- 网络超时、高德业务错误、空结果或未配置 Key 时自动回退现有 Mock 路线，
  回退结果保持 `source=MOCK`，**不会**标成高德真实数据。
- Key 只从环境变量读取：优先 `AMAP_API_KEY`，兼容旧名 `MAP_API_KEY`；
  两者都为空时不发任何 HTTP 请求，直接回退。
- 进程内缓存按「起点 / 终点 / 出发时间 / 允许方式」缓存成功的高德结果，
  规划与攻略阶段对完全相同的路线只请求一次。
- Provider 只把地理坐标发给高德：先用当前成都 Mock 资源目录把资源 ID
  解析成经纬度，解析不到就不发请求（绝不把资源 ID 当坐标）。

```powershell
cd backend
$env:DATA_MODE="HYBRID"
$env:AMAP_API_KEY="你的高德Web服务Key"   # 只放环境变量，不要写进代码或提交
python -m app.mcp_server
```

**数据真实性边界**：HYBRID 模式下只有本地路线可能来自高德，
景点 / 住宿 / 餐饮 / 天气 / 城际 / 准备规则仍是 Mock；整体仍是含 Mock 的
DEMO，前端必须继续显示 Mock 警告（`MOCK_DATA_IN_DEMO`），
单条路线来源看 `RouteOption.source`。

## 运行 A 线 MCP Server

P0 默认使用 Mock 数据，不需要地图、天气或 LLM API Key：

```powershell
cd backend
$env:DATA_MODE="MOCK"
python -m app.mcp_server
```

默认使用 stdio；如需 Streamable HTTP：

```powershell
$env:MCP_TRANSPORT="streamable-http"
$env:MCP_PORT="8001"
python -m app.mcp_server.server
```

HTTP MCP 端点为 `http://127.0.0.1:8001/mcp`。

## 替换点（其他两条线接入位置）

| 替换点 | 位置 | 谁来替换 |
|---|---|---|
| `TripProfileParser` | `app/services/request_parser.py` | B2（LLM 提取） |
| `DestinationRecommender` | `app/services/destination_recommender.py` | B4（LLM 比较） |
| `MCPProvider`（9 个工具） | `app/providers/` + `app/mcp_server/` | A4；当前Mock实现已接通 |
| `SessionRepository` | `app/services/session_store.py` | P1 可换 MySQL |
| 装配与切换 | `app/api/deps.py` | 上述替换只需改这一个文件 |

## 给 A / B 两条线的约定

- 只能 `from app.schemas import ...`，不得复制 Schema 定义到自己的模块。
- ⚠️ v0.4 模型目前**不会拒绝契约之外的字段**（会静默忽略；v0.3 的 `extra="forbid"`
  没有迁移过来）。见 `docs/contract-open-questions.md` 5.3 Q5——在三人拍板前，
  请不要往契约对象里塞自定义字段。
- 仓库根目录 `fixtures/` 下的 JSON 是三条线共用的示例数据源，可直接读取；
  修改前请先确认契约。
- `docs/contract-open-questions.md` 记录了契约中尚未确认的取值集合，
  收紧前不要依赖这些字段做枚举判断。


