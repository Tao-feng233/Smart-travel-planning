# backend —— 后端开发说明

> 三条开发线的共享进度台账见仓库根目录的 `PROGRESS_REPORT.md`；
> 契约待确认项见 `docs/contract-open-questions.md`。

## 当前状态（步骤 5 完成）

已实现共享契约对象（v0.4，旧 v0.3 已删除）、LangGraph 追问/推荐回路、
**C3 前置过滤（服务层 + 接入图）**和会话 REST 接口（统一响应信封）。
尚未实现行程生成、验证与修复、通用重规划（C4–C6）。

```text
backend/
├── app/
│   ├── api/           REST 路由与依赖注入（会话接口已完成）
│   ├── core/          运行期配置
│   ├── graph/         LangGraph 阶段、状态节点与工作流（C2 + C3）
│   ├── schemas/       共享契约对象 v0.4（唯一来源）
│   │   └── v04/       基线模型 / MCP 工具 / REST / 状态
│   ├── providers/     A线统一Provider协议与工厂
│   ├── mcp_server/    A线九工具强类型MCP Server
│   ├── main.py        FastAPI 应用入口
│   └── services/      缺失字段判定、提取、推荐、前置过滤、Mock Provider、会话存储
├── tests/
│   └── ...            118 个用例
└── requirements.txt
```

契约测试数据在**仓库根目录**的 `fixtures/`（三条线共用），
自检脚本是 `python contracts/validate_fixtures.py`。

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

当前结果：`118 passed`；根目录契约校验为 7 个合法、7 个非法、3 个业务用例通过。

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

