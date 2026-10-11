# 脚本使用导航

从项目根目录运行。根目录 `.env` 是默认配置入口；启动器保留原路径，其他脚本按用途整理，项目根路径和文档命令已同步。

| 用途 | 脚本 |
| --- | --- |
| 本机启动 | `scripts/start.py`，由根目录 `启动.cmd` / `启动.ps1` 调用 |
| 便携包启动与检查 | `scripts/launch.py`；仅检查用 `python scripts/launch.py --check --no-browser` |
| 知识采集与索引 | `scripts/data/`：`collect_knowledge.py`、`build_knowledge_index.py`、`import_legacy.py` |
| 数据与模型验证 | `scripts/checks/`：`check_data_service.py`、`check_goal_intents.py`、`eval_chunk_sizes.py`、`evaluate_prompt_refactor.py` |
| 当前隔离浏览器回归 | `scripts/checks/`：计划恢复、推荐卡片、可选房型、逐晚住宿、时间轴工具、辅助弹窗、计划展示和旅行隔离场景 |
| 真实供应商联调 | `scripts/integration/`：带 `live` 的场景、`check_live_locations.py`、`verify_choices_live.py`、`probe.py`、完整账户流程；会使用接口额度或创建测试账户 |
| 便携包制作与校验 | `scripts/release/`：`build_trial.py`、`verify_trial_package.py` |
| 历史检查与仓库迁移 | `scripts/legacy/`：历史浏览器场景、`prepare_repository_migration.py`、`prepare_migration_upload.py`、`read_migration_upload.py`；不是日常验收或启动步骤 |

当前隔离浏览器验收入口：

- `scripts/checks/browser_plan_recovery.cjs`：计划导航、刷新登录、旧计划与午夜边界。
- `scripts/checks/browser_recommendation_cards.cjs`：偏好询问、价格、推荐和景区层级。
- `scripts/checks/browser_optional_hotel_room.cjs`、`browser_time_stay.cjs`：房型可选、逐晚住宿和审核。
- `scripts/checks/browser_timeline_tools.cjs`：调整时间轴、交通方式与耗时显示。
- `scripts/checks/browser_assistance.cjs`、`browser_plan_visuals.cjs`：确认弹窗、计划展示、地图按需加载和打印。
- `scripts/checks/browser_history_map_ticket.cjs`：旅行切换、地图标记和票价适用范围。

以上入口拦截业务 HTTP，使用合成夹具，不操作真实旅行。Playwright 通过 `NODE_PATH` 提供，Chrome 路径可用 `BROWSER_PATH` 指定；旧场景可能仍依赖当时的界面和本机路径，不纳入当前验收。

`python scripts/checks/evaluate_prompt_refactor.py --after-only` 只检查评估准备；添加 `--live` 才会调用模型，不执行业务工具或保存旅行。`check_data_service.py` 验证本地知识服务，添加其明确的实时查询选项才联调外部地点。

构建默认不带 `.env`、账户、旅行记录、备份或运行缓存。`--include-env` 会包含凭据，仅用于所有者明确授权的分享，不上传公共仓库。
