"""B 线 LLM 层：需求提取（B2）、目的地比较（B4）、修改意图识别（B5）。

`AGENTS.md`「建议代码边界」把 `backend/app/llm/` 划归 B 线
（「LLMProvider与需求/决策服务」）。

本层只做「把用户的话翻译成契约对象」这一件事，**不产生任何旅游事实**：
开放时间、价格、路线、住宿、餐饮、天气一律来自数据层 / MCP 工具 / RAG 证据。
每个解析器都在输出前做机械红线校验（见 `guards.py`），失败则明确降级到
C 线的规则式实现，降级原因写进各自的 `diagnostics`。

典型装配（`app/api/deps.py`）：

```python
from app.llm import (
    LLMDestinationRecommender,
    LLMTripProfileParser,
    get_llm_provider,
)

provider = get_llm_provider()
deps = NodeDeps(
    parser=LLMTripProfileParser(provider=provider),
    recommender=LLMDestinationRecommender(provider=provider),
    ...
)
```
"""

from .action_interpreter import (
    InterpretedAction,
    LLMUserActionInterpreter,
    RuleBasedUserActionInterpreter,
    UserActionInterpreter,
)
from .destination_recommender import LLMDestinationRecommender, RecommendOutcome
from .provider import (
    LLMProvider,
    LLMSettings,
    LLMUnavailableError,
    NullLLMProvider,
    OpenAICompatibleProvider,
    build_provider,
    describe_channel,
    get_llm_provider,
    load_settings,
    reset_llm_provider,
)
from .request_parser import LLMTripProfileParser, ParseOutcome

__all__ = [
    "InterpretedAction",
    "LLMDestinationRecommender",
    "LLMTripProfileParser",
    "LLMProvider",
    "LLMSettings",
    "LLMUnavailableError",
    "LLMUserActionInterpreter",
    "NullLLMProvider",
    "OpenAICompatibleProvider",
    "ParseOutcome",
    "RecommendOutcome",
    "RuleBasedUserActionInterpreter",
    "UserActionInterpreter",
    "build_provider",
    "describe_channel",
    "get_llm_provider",
    "load_settings",
    "reset_llm_provider",
]
