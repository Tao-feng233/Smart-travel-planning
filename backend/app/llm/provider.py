"""LLM 通道（B 线）。

设计约束（`AGENTS.md`「技术约束」/ `docs/MODEL_PROVIDER_AND_SECRETS.md`）：

* Key 只从环境变量读取，不写进代码、文档、日志或测试；
* 业务服务不得写死模型平台、Base URL 或模型名 —— 一律走 `LLMSettings`；
* 任何失败（未配置、超时、返回非法 JSON）都必须能被上层**明确降级**，
  不允许静默吞掉失败，更不允许用模型记忆顶替数据。

用 `httpx` 直接请求 OpenAI 兼容的 `/chat/completions`，而不是引入各家 SDK：
`backend/requirements.txt` 里已有 `httpx`，这样换平台只改环境变量，
不需要装新包，也不在代码里绑定任何一家平台。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

def _find_repo_root() -> Path:
    """从本文件向上找仓库根：含 `.env.example` 或 `.git` 的那一层。

    不要写死"上溯几层"——本文件在 `backend/app/llm/` 下，
    `.env.example` 由团队约定放在**仓库根**（与 `.gitignore` 同级），
    写死层级很容易差一层，导致 `.env` 静默读不到、通道一直显示 disabled。
    """

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".env.example").is_file() or (candidate / ".git").exists():
            return candidate
    # 兜底：backend/app/llm/provider.py → 仓库根
    return here.parents[3] if len(here.parents) > 3 else here.parent


#: 仓库根目录
_REPO_ROOT = _find_repo_root()

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_TOKENS = 2048

#: 一次调用最多重试几轮（含首次）；数字越大越慢，P0 取 2 足够
_MIN_ATTEMPTS = 1


class LLMUnavailableError(RuntimeError):
    """没有任何可用的 LLM：未配置 Key，或调用连续失败。"""


class JsonModeUnsupported(RuntimeError):
    """平台不认 `response_format={"type": "json_object"}`，需要退回纯提示词约束。"""


@dataclass(frozen=True)
class LLMSettings:
    """一组模型配置。除了 `describe()`，其余字段都不得写进日志。"""

    provider: str
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    def describe(self) -> str:
        """可安全落日志的描述（**绝不包含 Key**）。"""

        return f"{self.provider}/{self.model} @ {self.base_url}"


# --- 配置读取 ---------------------------------------------------------------


def load_dotenv(path: str | Path | None = None) -> None:
    """把仓库根目录的 `.env` 读进 `os.environ`，**不覆盖已有变量**。

    只做最小解析（`KEY=VALUE`、跳过注释与空行、去掉成对引号）。
    自己实现而不引入 `python-dotenv`，是为了不往 `requirements.txt` 里加依赖。
    """

    if path is not None:
        candidates = [Path(path)]
    else:
        # 仓库根优先；兼容"在 backend/ 下启动"时把 .env 放在当前目录的写法
        candidates = [_REPO_ROOT / ".env", Path.cwd() / ".env"]

    env_path = next((item for item in candidates if item.is_file()), None)
    if env_path is None:
        return
    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - 读不到就当作没配置
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("环境变量 %s 不是数字（%r），改用默认值 %s", name, raw, default)
        return default


def load_settings(prefix: str = "LLM_PRIMARY_") -> LLMSettings | None:
    """按前缀读一组配置；缺少 Key / Base URL / 模型名时视为「未配置」。"""

    load_dotenv()
    api_key = (os.environ.get(f"{prefix}API_KEY") or "").strip()
    base_url = (os.environ.get(f"{prefix}BASE_URL") or "").strip()
    model = (os.environ.get(f"{prefix}MODEL") or "").strip()
    if not (api_key and base_url and model):
        return None
    provider = (os.environ.get(f"{prefix}PROVIDER") or "").strip() or "openai-compatible"
    return LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_retries=int(_float_env("LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
    )


# --- 协议 -------------------------------------------------------------------


class LLMProvider(Protocol):
    """B 线各解析器依赖的最小接口。

    只暴露「要一段 JSON 回来」这一个能力：结构化输出由调用方用 Pydantic
    对着共享 Schema 校验，Provider 本身不做业务判断。
    """

    name: str
    is_available: bool

    def complete_json(
        self, *, system: str, user: str, max_retries: int | None = None
    ) -> dict[str, Any]: ...


# --- 实现 -------------------------------------------------------------------


PostFunc = Callable[[str, dict[str, Any], dict[str, str]], str]


class OpenAICompatibleProvider:
    """OpenAI 兼容协议的通用实现（DeepSeek / 百炼 / 智谱 / 火山 / 硅基流动 等通用）。"""

    def __init__(self, settings: LLMSettings, *, post: PostFunc | None = None) -> None:
        self._settings = settings
        self._post = post
        self.name = settings.provider
        self.is_available = True

    @property
    def settings(self) -> LLMSettings:
        return self._settings

    def complete_json(
        self, *, system: str, user: str, max_retries: int | None = None
    ) -> dict[str, Any]:
        attempts = max(
            _MIN_ATTEMPTS,
            self._settings.max_retries if max_retries is None else max_retries,
        )
        last_error: Exception | None = None
        json_mode = True
        attempt = 0

        while attempt < attempts:
            attempt += 1
            try:
                text = self._request(system, user, json_mode=json_mode)
                return _loads_json_object(text)
            except JsonModeUnsupported as exc:
                if not json_mode:
                    # 已经退回纯提示词还是不行，按普通失败处理
                    last_error = exc
                    continue
                logger.info("平台不支持 response_format，改用提示词约束 JSON：%s", exc)
                json_mode = False
                attempt -= 1  # 换协议格式不算一次重试
                continue
            except Exception as exc:  # noqa: BLE001 - 统一转成可降级的失败
                last_error = exc
                logger.warning(
                    "LLM 第 %s/%s 次调用失败（%s）：%s",
                    attempt,
                    attempts,
                    self._settings.describe(),
                    _mask(str(exc), self._settings.api_key),
                )

        raise LLMUnavailableError(
            f"LLM 连续 {attempts} 次调用失败："
            f"{_mask(_safe_message(last_error), self._settings.api_key)}"
        )

    # --- 内部 ---------------------------------------------------------------

    def _endpoint(self) -> str:
        base = self._settings.base_url
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, system: str, user: str, *, json_mode: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # 提取任务要可复现，温度固定 0
            "temperature": 0,
            "max_tokens": DEFAULT_MAX_TOKENS,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _request(self, system: str, user: str, *, json_mode: bool) -> str:
        payload = self._payload(system, user, json_mode=json_mode)
        if self._post is not None:  # 测试注入，避免真联网
            return self._post(self._endpoint(), payload, self._headers())

        import httpx

        try:
            with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                response = client.post(
                    self._endpoint(), json=payload, headers=self._headers()
                )
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(f"LLM 请求超时（{self._settings.timeout_seconds}s）") from exc

        if (
            response.status_code == 400
            and json_mode
            and "response_format" in response.text
        ):
            raise JsonModeUnsupported(response.text[:200])

        response.raise_for_status()
        return _extract_content(response.json())


class NullLLMProvider:
    """未配置模型接口时的占位实现。

    调用会立刻失败，让上层走**明确的降级路径**（规则式 STUB），
    而不是静默返回空结果 —— 静默会让「资料不足」变成「看起来成功」。
    """

    name = "disabled"
    is_available = False

    def complete_json(
        self, *, system: str, user: str, max_retries: int | None = None
    ) -> dict[str, Any]:
        raise LLMUnavailableError(
            "未配置可用的大模型接口（需要 LLM_PRIMARY_API_KEY / BASE_URL / MODEL）"
        )


# --- 工厂 -------------------------------------------------------------------

_provider: LLMProvider | None = None


def build_provider(
    *, primary_prefix: str = "LLM_PRIMARY_", fallback_prefix: str = "LLM_FALLBACK_"
) -> LLMProvider:
    """优先主通道，其次备用通道，都没有则返回 `NullLLMProvider`。"""

    for prefix in (primary_prefix, fallback_prefix):
        settings = load_settings(prefix)
        if settings is not None:
            return OpenAICompatibleProvider(settings)
    return NullLLMProvider()


def get_llm_provider() -> LLMProvider:
    """进程内单例（读一次环境变量即可）。"""

    global _provider
    if _provider is None:
        _provider = build_provider()
        logger.info("LLM 通道已装配：%s", _provider.name)
    return _provider


def reset_llm_provider() -> None:
    """清空单例（测试或刚改完环境变量时用）。"""

    global _provider
    _provider = None


def describe_channel() -> dict[str, str]:
    """不泄露 Key 的通道状态，便于联调时确认「模型到底接上了没有」。"""

    provider = get_llm_provider()
    info = {"provider": provider.name, "available": str(provider.is_available)}
    settings = getattr(provider, "settings", None)
    if isinstance(settings, LLMSettings):
        info["model"] = settings.model
        info["base_url"] = settings.base_url
    return info


# --- 工具 -------------------------------------------------------------------


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM 响应里没有 choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM 响应内容为空")
    return content


def _loads_json_object(text: str) -> dict[str, Any]:
    """把模型输出解析成 JSON 对象，容忍 markdown 代码块与前后解释文字。"""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM 输出不是 JSON 对象") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM 输出不是合法 JSON：{exc}") from None

    if not isinstance(parsed, dict):
        raise ValueError("LLM 输出的 JSON 顶层不是对象")
    return parsed


def _mask(text: str, secret: str) -> str:
    """日志安全：万一异常信息里带了 Key，替换掉。"""

    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def _safe_message(exc: Exception | None) -> str:
    if exc is None:
        return "未知错误"
    return f"{type(exc).__name__}: {exc}"[:300]


__all__ = [
    "LLMSettings",
    "LLMProvider",
    "LLMUnavailableError",
    "JsonModeUnsupported",
    "NullLLMProvider",
    "OpenAICompatibleProvider",
    "build_provider",
    "describe_channel",
    "get_llm_provider",
    "load_dotenv",
    "load_settings",
    "reset_llm_provider",
]
