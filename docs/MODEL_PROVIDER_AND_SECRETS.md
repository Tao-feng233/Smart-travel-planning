# 模型Provider与密钥配置

## 1. 设计目标

业务代码不直接依赖某一家模型平台。第一版先接通一个主模型，但从开始就通过统一 `LLMProvider` 调用；后续增加备用Provider时不修改需求理解、LangGraph和攻略组装逻辑。

当前考虑的具体模型名称、API地址和能力均为待验证项，不写死在代码和契约中。

## 2. LLMProvider能力

```text
LLMProvider
├── chat(messages)
├── structured_output(messages, schema)
├── tool_call(messages, tools)
├── health_check()
└── provider_name/model_name
```

所有模型输出都必须经过Pydantic校验。Provider只解决模型调用，不负责旅游数据获取。

## 3. 主备模型策略

### P0

- 实现一个主Provider。
- 配置中预留备用Provider。
- 统一超时、有限次数重试和错误记录。

### P1

- 主模型遇到超时、限流或服务端错误时切换备用Provider。
- 业务校验失败不直接换模型，应先修复提示或重试结构化输出。
- 切换模型后仍必须执行相同的候选ID、证据和约束校验。

## 4. 本地密钥配置

本地开发使用项目根目录 `.env`，部署环境使用系统环境变量或密钥管理服务。Vue前端不得持有任何服务端API Key。

### `.env.example`

```env
LLM_PRIMARY_PROVIDER=
LLM_PRIMARY_API_KEY=
LLM_PRIMARY_BASE_URL=
LLM_PRIMARY_MODEL=

LLM_FALLBACK_PROVIDER=
LLM_FALLBACK_API_KEY=
LLM_FALLBACK_BASE_URL=
LLM_FALLBACK_MODEL=

LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2

MAP_API_KEY=
WEATHER_API_KEY=
```

### `.gitignore`

```gitignore
.env
.env.*
!.env.example
```

## 5. 安全规则

- 不在代码、前端、Markdown、截图和日志中保存真实Key。
- AI助手不得请求成员把真实Key粘贴到对话中。
- 后端日志对认证Header和Key字段脱敏。
- 不同Provider分别配置Key、Base URL和模型名。
- 启动时缺少必要Key要给出明确错误，不使用代码中的默认密钥。

