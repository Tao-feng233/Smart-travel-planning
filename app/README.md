# 后端模块导航

启动入口仍为 `app.main:app`。后端按职责分目录，原根目录模块已迁移，源码、测试与维护脚本使用同一套新路径；没有保留两套业务实现。

| 职责 | 主要文件 |
| --- | --- |
| 服务启动与关闭 | `main.py`：组装路由，启动 MCP，关闭任务和连接 |
| HTTP 与账户 | `api/`：路由、鉴权、请求校验、SSE 与响应安全策略 |
| 应用编排与展示 | `application/jobs.py`：任务执行、取消、关闭；`job_progress.py`、`turn_state.py`、`post_processing.py`、`job_results.py`：进度、状态比较、预演审核、收尾保存；`workspaces.py`：工作台数据；`guidance.py`、`report.py`：展示与导出 |
| 模型主链 | `agents/planner.py` 组装主链；`input_context.py` 提供事实，`turn.py` 执行一轮对话；`goals.py`、`execution.py`、`edit_tools.py` 连续完成工具操作；`auto_selection.py` 处理授权代选；`replies.py` 汇报结果 |
| 旅行需求与选择 | `travel/dispatch.py`、`handlers/`：按业务分发和处理动作；`requirements.py` 校验需求，`selections.py` 清理取消选择；`actions.py` 提供草稿提交边界 |
| 景点与住宿查询 | `travel/discovery.py`、`spot_search.py`：展示分页、分批获取、筛选和发布；`hotels.py`、`hotel_candidates.py`：逐晚住宿查询、详情与统一酒店候选资料 |
| 时间轴与排程 | `planning/engine.py` 组装生成流程；`plan_inputs.py`、`plan_routes.py`、`daily_schedule.py`、`meal_events.py`、`plan_output.py`、`plan_review.py` 分别负责提案、道路、全天排程、用餐、输出与审核；`return_fitting.py` 用实际餐次与道路试排返程日弹性游览，`route_cache.py` 复用本次道路查询；`schedule.py` 构建工作台预览 |
| 配置与共享约定 | `core/`：配置、错误、文本处理及平台接口约定 |
| 外部接口与 MCP | `integrations/`：供应商适配、地图、缓存与 MCP；`contracts.py` 校验外部数据形状及坐标 |
| 途牛轮换与额度 | `integrations/tuniu.py`、`tuniu_pool.py`、`tuniu_policy.py` |
| 知识服务 | `knowledge/`：采集、覆盖判断、语料、混合检索、Embedding 与索引 |
| 数据保存 | `persistence/storage.py`：SQLite 账户、旅行、版本、任务与有限期缓存 |
| 提示词 | `prompts/`：阶段模板与加载器 |

## 导入与运行路径

```python
from app.agents import planner
from app.travel import journey, stay_plan
from app.planning import engine, timeline_tools
from app.integrations import providers
from app.knowledge import retrieval
from app.persistence import storage
from app.core.config import ROOT, setting
from app.core.errors import DataError
```

原 `app.agent` → `app.agents.planner`，原 `app.planning` 生成器 → `app.planning.engine`，原 `app.rag` → `app.knowledge.retrieval`。原 `app.main` 中的任务执行与页面数据整理分别位于 `application/jobs.py` 和 `application/workspaces.py`。

任务状态只有一份注册表。MCP 进程入口改为 `app/integrations/mcp_server.py`，启动与数据检查脚本已同步。根目录 `.env`、`data/runtime/travel.db`、模型缓存、知识索引和前端资源路径保持不变；环境配置修改后仍需重启服务。

途牛调用经 `integrations/providers.py` 委托到途牛适配器；四账号轮换、共享账号限速与计量规则保持原行为。凭据仅从本机配置读取。

模型编辑执行链由 `agents/edit_tools.py`、`agents/execution.py` 和 `travel/actions.py` 提供，后台入口复用同一提交边界；见 [编辑工具说明](../docs/releases/模型编辑工具与连续执行-20261011.md)。动作分发、后台任务、住宿查询和推荐已按职责拆分。意图执行、计划生成、提示词、前端和脚本整理也已收尾，见 [整体完成与复审记录](../docs/releases/整体重构完成与复审-20261011.md)。
