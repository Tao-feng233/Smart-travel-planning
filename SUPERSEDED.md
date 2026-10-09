# 本分支已 Superseded，请勿在此基础上继续开发或合入

**请改用：`feat/shitu-v12-arrival-and-return`**

## 原因

本分支（`feat/shitu-v12-planning`）是最早的开发分支，其逐晚住宿、时间口径、
景点去重、房型弹窗等实现均已整合进 `feat/shitu-v11-review-integration`，
并在整合过程中被修正（其中多项修正优于本分支原写法）。

本分支保留仅作**历史来源**，不应再作为合入对象。

## 正确做法

按整合文档的同步方式执行：

```bash
git fetch origin
git checkout -b <你的工作分支> origin/feat/shitu-v11-review-integration
```

**不要**逐段复制 `agent.py`、**不要**用整文件覆盖最新代码、
**不要**再合入本分支或用它恢复旧实现。

## 详见

`docs/collaboration/成员三分支交接-抵达日与返程日审查-20261009.md`
（在 `feat/shitu-v12-arrival-and-return` 上）
