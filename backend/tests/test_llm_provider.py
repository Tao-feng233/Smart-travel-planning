"""B2/B4/B5 共用通道（`app/llm/provider.py`）测试。

重点是**配置能不能被读到**：这个文件曾经把仓库根算成了 `backend/`，
于是 `.env` 静默读不到、通道一直显示 `disabled`，而且不报任何错。
所以这里专门锁住"上溯到含 `.env.example` 的那一层"这条行为。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.provider import (
    LLMSettings,
    _find_repo_root,

    get_llm_provider,
    load_dotenv,
    load_settings,
    reset_llm_provider,
)

def test_repo_root_is_the_directory_holding_env_example() -> None:
    """团队约定 `.env.example` 与 `.gitignore` 同级放在仓库根。

    `provider.py` 在 `backend/app/llm/` 下，写死"上溯几层"很容易差一层。
    """

    root = _find_repo_root()
    assert (root / ".env.example").is_file(), f"{root} 下没有 .env.example"
    assert (root / "backend").is_dir()

def test_load_dotenv_reads_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 必须先清干净：同一进程里前面的用例可能已经从真实 .env 里读进过这两个变量，
    # 而 load_dotenv 按设计"不覆盖已有值"，残留会让本用例假失败
    monkeypatch.delenv("LLM_PRIMARY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PRIMARY_BASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 注释行\n"
        "\n"
        "LLM_PRIMARY_API_KEY=sk-test-123\n"
        "LLM_PRIMARY_BASE_URL=\"https://example.invalid/v1\"\n",
        encoding="utf-8",
    )

    load_dotenv(env_file)

    import os

    assert os.environ["LLM_PRIMARY_API_KEY"] == "sk-test-123"
    # 成对引号要被去掉
    assert os.environ["LLM_PRIMARY_BASE_URL"] == "https://example.invalid/v1"

def test_load_dotenv_never_overrides_existing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式设置的环境变量优先于 `.env`（部署时用系统变量覆盖本地文件）。"""

    import os

    monkeypatch.setenv("LLM_PRIMARY_API_KEY", "sk-from-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PRIMARY_API_KEY=sk-from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert os.environ["LLM_PRIMARY_API_KEY"] == "sk-from-shell"

def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    load_dotenv(tmp_path / "不存在的.env")  # 不抛异常即通过

def test_describe_never_exposes_the_key() -> None:
    settings = LLMSettings(
        provider="openai-compatible",
        api_key="sk-super-secret-value",
        base_url="https://example.invalid/v1",
        model="demo-model",
    )
    text = settings.describe()
    assert "sk-super-secret-value" not in text
    assert "demo-model" in text

def test_missing_key_means_disabled_not_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺 Key 只表示"通道未启用"，不是错误——三处调用点都据此降级到规则式。"""

    # 把仓库根与工作目录都指到临时目录，避免读到开发机上的真实 .env
    monkeypatch.setattr("app.llm.provider._REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_PRIMARY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PRIMARY_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_PRIMARY_MODEL", "demo-model")

    assert load_settings("LLM_PRIMARY_") is None

def test_env_file_is_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有 `.env` 也必须能正常导入——否则没配 Key 的同学连测试都跑不了。"""

    monkeypatch.setattr("app.llm.provider._REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_PRIMARY_API_KEY", raising=False)

    assert load_settings("LLM_PRIMARY_") is None

def test_reset_clears_the_cached_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试之间必须能重置单例，否则一个用例的配置会污染后面的用例。"""

    monkeypatch.setattr("app.llm.provider._REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_PRIMARY_API_KEY", raising=False)

    reset_llm_provider()
    assert get_llm_provider().__class__.__name__ == "NullLLMProvider"
