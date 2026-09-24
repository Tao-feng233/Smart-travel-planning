# 三人协作交接说明

三个成员各自一台电脑，因此需要显式同步。本目录放**可以直接复制粘贴**给对方（或对方的 AI 助手）的说明文档。

## 文件

| 文件 | 给谁 | 用途 |
|---|---|---|
| `A_交接说明.md` | 成员 A（数据、RAG 与 MCP） | 让对方从零拿到项目状态并开工 |
| `B_交接说明.md` | 成员 B（LLM 决策与 Vue 前端） | 同上 |

## 为什么需要它

`PROGRESS_REPORT.md` 是共享进度台账，但它假设对方已经能看到仓库文件。
各自一台电脑时，对方的 AI 助手读不到仓库，所以必须先给出一段
**自包含的上下文**：项目是什么、已经做到哪、他们要做什么、边界在哪。

## 同步方式：Git 远程仓库（已建好）

```bash
git clone https://github.com/Tao-feng233/Smart-travel-planning
cd Smart-travel-planning
```

| 成员 | 分支 | 切换命令 |
|---|---|---|
| A | `feature/data-rag-mcp` | `git checkout feature/data-rag-mcp` |
| B | `feature/llm-vue` | `git checkout feature/llm-vue` |
| C | `feature/graph-planner` | `git checkout feature/graph-planner` |

**仓库根目录就是 `Smart-travel-planning` 这一层**，
`AGENTS.md`、`CONTRACTS.md` 都在根目录，不要进到子目录里去找。

**如果 clone 时报连不上 github.com**：说明需要代理（国内网络常见）。
临时用法：

```bash
git -c http.proxy=http://127.0.0.1:7897 clone https://github.com/Tao-feng233/Smart-travel-planning
```

（端口按自己机器的代理软件改；也可以只为本仓库配置：
`git config http.proxy http://127.0.0.1:7897`）

**必须遵守**：

- `.env` 不得传给任何人，各自按 `.env.example` 建本地文件。
- 每人在自己的分支上开发，不要直接改 `main`。
- 修改 `CONTRACTS.md` 前必须三人确认（先改文档，再改代码）。

## 使用步骤

1. 对方从上面的仓库地址 clone，并切到自己的分支。
2. 把对应角色的 `*_交接说明.md` 发给对方（或直接让对方打开本目录下的文件）。
3. 对方把文档里的「提示词」整段复制给自己电脑上的 AI 助手。
4. 对方的 AI 应先复述边界、输入、输出、依赖，再开始写代码。

## 开工前建议先看的四份

| 文件 | 作用 |
|---|---|
| `README.md`（仓库根目录） | 项目入口、仓库结构、文档索引 |
| `PROGRESS_REPORT.md` 的「⚡ 最新变更」 | 当前进度，以及**需要你做什么** |
| `docs/contract-open-questions.md` | 契约里还没定死的地方，改动前必看 |
| `docs/requirements/` | 用户最初提的需求，以及它们对应到项目里的哪些部分 |
