# 后端模块导航

当前启动入口仍是 `app.main:app`。为方便三人协作，已有业务模块保留原导入路径；外部途牛连接与账号调度移入 `integrations/`。

| 职责 | 主要文件 |
| --- | --- |
| API、任务与账户 | `main.py`、`auth.py`、`storage.py` |
| 配置与共享数据契约 | `config.py`、`data_settings.py`、`data_contracts.py`、`contracts.py` |
| 模型理解、目标执行与回复 | `agent.py`、`goal_agent.py`、`auto_selection.py`、`replies.py` |
| 外部数据与 MCP | `providers.py`、`tools.py`、`mcp_server.py`、`integrations/tuniu.py` |
| 途牛账号轮换、额度与冷却 | `integrations/tuniu_pool.py` |
| 目的地、景点与资料核对 | `discovery.py`、`data_coverage.py`、`enrichment.py`、`locations.py`、`spot_hierarchy.py` |
| 住宿、餐饮及选项 | `stay_plan.py`、`foods.py`、`choices.py`、`access.py` |
| 时间轴、排程与计划书 | `schedule.py`、`planning.py`、`proposals.py`、`timeline_tools.py`、`travel_preview.py`、`transport_links.py` |
| 时间策略、诊断与复核 | `pacing.py`、`time_policy.py`、`visit_analysis.py`、`timeline_review.py`、`diagnostics.py`、`plan_warnings.py`、`plan_revision.py` |
| 知识采集与检索 | `knowledge_collection.py`、`public_fetch.py`、`public_directory.py`、`knowledge.py`、`rag.py`、`embeddings.py`、`vector_index.py` |
| 呈现、地图与导出 | `guidance.py`、`price_hints.py`、`maps.py`、`report.py` |

业务代码继续调用 `providers.tuniu()`；该入口是兼容外观，内部委托给途牛适配器。账号轮换不改变选定酒店/班次的业务身份，也不引入预订工具。所有账号凭据仅从本机 `.env` 读取。
