# 脚本使用导航

从项目根目录运行脚本，根目录 `.env` 是唯一默认配置入口。历史浏览器脚本保留原位置，避免破坏已有验证命令；按用途区分如下。

| 用途 | 脚本 |
| --- | --- |
| 本机启动 | `start.py`，由根目录 `启动.cmd` / `启动.ps1` 调用 |
| 便携包启动与检查 | `launch.py`；仅检查用 `python scripts/launch.py --check --no-browser` |
| 知识采集与索引 | `collect_knowledge.py`、`build_knowledge_index.py`、`import_legacy.py` |
| 数据与模型验证 | `check_data_service.py`、`check_goal_intents.py`、`eval_chunk_sizes.py` |
| 当前隔离浏览器回归 | `browser_plan_recovery.cjs`、`browser_timeline_tools.cjs`、`browser_recommendation_cards.cjs`、`browser_assistance.cjs`、`browser_optional_hotel_room.cjs`、`browser_time_stay.cjs` |
| 真实供应商联调 | 文件名带 `live` 的脚本，以及 `check_live_locations.py`、`verify_choices_live.py`、`probe.py`；运行前确认查询范围和额度 |
| 便携包制作与校验 | `build_trial.py`、`verify_trial_package.py` |
| 历史仓库迁移 | `prepare_repository_migration.py`、`prepare_migration_upload.py`、`read_migration_upload.py`；不是日常启动步骤 |

浏览器回归所需 Playwright 和 Chrome 路径按本机环境设置。真实联调脚本会消耗供应商额度；隔离回归使用测试夹具，不证明实时供应商数据或运营条件。

构建默认不带 `.env`；`--include-env` 分享包包含所有已配置凭据，仅限所有者明确授权的本机分享，不上传公开仓库。
