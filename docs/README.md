# 项目文档导航

项目运行入口是根目录的 `启动.cmd` / `启动.ps1`，配置是根目录 `.env`。先阅读 [项目说明](../README.md)，再根据任务选择文档。

| 目录 | 内容 | 使用方式 |
| --- | --- | --- |
| [design](design/项目文档.md) | 业务流程、功能结构、项目方案、原型评审和地图设计 | 解释项目设计；历史设想以当前代码为准 |
| [reference](reference/官方接口核对.md) | 外部接口核对与途牛文档快照 | 实时字段以供应商文档和 MCP schema 为准 |
| [status](status/开发状态.md) | 早期开发状态记录 | 当前实现优先查看更新记录与 CONTEXT |
| [collaboration](collaboration/) | 三人分工、接口契约与分批整合说明 | 组员对接 |
| [releases](releases/) | 每次已完成修改的行为、验证和边界 | 查看最新改动 |
| [legacy](legacy/README.md) | 旧项目参考资料 | 保留历史，不代表当前运行实现 |

当前新增配置说明：[途牛多账号轮换](releases/途牛多账号轮换与目录整理-20261009.md)。

实现导航：[后端模块](../app/README.md)、[脚本](../scripts/README.md)、[历史原型](../prototypes/README.md)。

本机 `output/` 保存汇报稿、导出图表和审查报告，`data/runtime/` 保存运行数据、日志、测试记录及上传暂存。二者均不作为公开源码发布；不要把实际 `.env`、账户数据库或配置分享包提交到 GitHub。
