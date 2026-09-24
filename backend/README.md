# backend —— C 线开发说明

> 三条开发线的共享进度台账见仓库根目录的 `PROGRESS_REPORT.md`。

## 当前状态（第 1 步完成）

已实现共享 Pydantic 契约对象，尚未实现 LangGraph 工作流、规划器和 API。

```text
backend/
├── app/
│   ├── api/           FastAPI 路由（C7 阶段）
│   ├── graph/         LangGraph 状态与节点（C2 阶段）
│   ├── schemas/       共享契约对象（已完成 C1）
│   └── services/      前置过滤、规划、验证、修复（C3–C6 阶段）
├── tests/
│   ├── fixtures/      契约示例 JSON，三条开发线共用
│   ├── test_contract_examples.py
│   └── test_contract_strictness.py
└── requirements.txt
```

## 环境

```powershell
cd backend
python -m pip install -r requirements.txt
```

本项目开发环境已验证：Python 3.12.7、pydantic 2.8.2、pytest 7.4.4。

## 运行测试

```powershell
cd backend
python -m pytest
```

## 给 A / B 两条线的约定

- 只能 `from app.schemas import ...`，不得复制 Schema 定义到自己的模块。
- 所有对象默认**禁止契约之外的字段**，多传一个键会直接抛 `ValidationError`。
- `tests/fixtures/` 下的 JSON 是三条线共用的示例数据源，可直接读取；
  修改前请先确认契约。
- `docs/contract-open-questions.md` 记录了契约中尚未确认的取值集合，
  收紧前不要依赖这些字段做枚举判断。
