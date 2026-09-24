# backend —— C 线开发说明

> 三条开发线的共享进度台账见仓库根目录的 `PROGRESS_REPORT.md`；
> 契约待确认项见 `docs/contract-open-questions.md`。

## 当前状态（第 2 步完成）

已实现共享契约对象、LangGraph 追问/推荐回路和会话 REST 接口。
尚未实现前置过滤、行程生成、验证与修复（C3–C6）。

```text
backend/
├── app/
│   ├── api/           REST 路由与依赖注入（会话接口已完成）
│   ├── core/          运行期配置
│   ├── graph/         LangGraph 阶段、状态节点与工作流（已完成 C2）
│   ├── schemas/       共享契约对象（已完成 C1）
│   │   └── api.py     REST 传输对象（不是领域契约）
│   ├── main.py        FastAPI 应用入口
│   └── services/      缺失字段判定、提取、推荐、MCP 客户端、会话存储
├── tests/
│   ├── fixtures/      契约示例 JSON，三条开发线共用
│   └── ...            80 个用例
└── requirements.txt
```

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
GET  /api/sessions/{id}             获取当前 PlanState 与助手回复
GET  /health                        健康检查
```

典型两轮对话：

```text
第 1 轮「我想出去玩，不想早起」        → 追问出发地/日期/人数/预算
第 2 轮「从上海出发，10月...2个人，预算5000元」 → 推荐候选 + 证据
```

## 运行测试

```powershell
cd backend
python -m pytest
```

## 替换点（其他两条线接入位置）

| 替换点 | 位置 | 谁来替换 |
|---|---|---|
| `TripProfileParser` | `app/services/request_parser.py` | B2（LLM 提取） |
| `DestinationRecommender` | `app/services/destination_recommender.py` | B4（LLM 比较） |
| `TravelMCPClient` | `app/services/travel_mcp_client.py` | A4（真实 MCP Server） |
| `SessionRepository` | `app/services/session_store.py` | P1 可换 MySQL |
| 装配与切换 | `app/api/deps.py` | 上述替换只需改这一个文件 |

## 给 A / B 两条线的约定

- 只能 `from app.schemas import ...`，不得复制 Schema 定义到自己的模块。
- 所有对象默认**禁止契约之外的字段**，多传一个键会直接抛 `ValidationError`。
- `tests/fixtures/` 下的 JSON 是三条线共用的示例数据源，可直接读取；
  修改前请先确认契约。
- `docs/contract-open-questions.md` 记录了契约中尚未确认的取值集合，
  收紧前不要依赖这些字段做枚举判断。
