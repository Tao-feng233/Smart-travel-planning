# 本分支已 Superseded，请勿在此基础上继续开发或合入

**请改用：`feat/shitu-v12-arrival-and-return`**

## 原因

本分支（`feat/shitu-v12-time-and-stay`）的提交已被整合进
`feat/shitu-v11-review-integration`，范围如下：

| 提交 | 状态 |
| --- | --- |
| `b6a3bed` … `118dfe1`（共 14 个） | **已被整合吸收** |
| `9834185`（选定班次后自动审查） | 未吸收；已在 `feat/shitu-v12-arrival-and-return` 中重做 |

整合过程还对本分支的实现做了多项修正，这些修正**优于本分支原写法**，
本分支不应再被合入，否则会把下列修正回退掉：

- `included_meal()` 的严格校验（房型归属、报价时效、入住区间、人数与儿童权益）
- `timeline_review.py` 的主动审核（程序检查 + 只读模型审核、缓存与去重）
- 候选折叠、房型可选且不自动弹窗、逐晚候选报价身份与缓存签名
- 「泛指含餐误判含早」的判定方向

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
