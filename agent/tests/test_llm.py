"""Tests for LLM factory and JSON extraction."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.providers.llm import _extract_balanced_json, build_llm


class TestBuildLLM:
    """build_llm reads LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME directly."""

    def _capture(self, env: dict[str, str]) -> dict:
        import src.providers.llm as llm_mod
        llm_mod._dotenv_loaded = True

        captured: dict = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        with patch.dict(os.environ, env, clear=True):
            with patch.object(llm_mod, "ChatOpenAIWithReasoning", _FakeChatOpenAI):
                build_llm()
        return captured

    def test_reads_llm_env_vars(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
            "LLM_API_KEY": "sk-or-test",
            "LLM_MODEL_NAME": "deepseek/deepseek-v3.2",
        })
        assert captured["model"] == "deepseek/deepseek-v3.2"
        assert captured["api_key"] == "sk-or-test"
        assert captured["base_url"] == "https://openrouter.ai/api/v1"

    def test_temperature_clamped_from_zero(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://api.minimax.io/v1",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL_NAME": "MiniMax-M2.7",
            "LLM_TEMPERATURE": "0.0",
        })
        assert captured["temperature"] == 0.01

    def test_positive_temperature_preserved(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://api.minimax.io/v1",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL_NAME": "MiniMax-M2.7",
            "LLM_TEMPERATURE": "0.7",
        })
        assert captured["temperature"] == 0.7

    def test_no_api_key_for_local(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "http://localhost:11434/v1",
            "LLM_MODEL_NAME": "qwen2.5:32b",
        })
        assert "api_key" not in captured
        assert captured["base_url"] == "http://localhost:11434/v1"

    def test_raises_without_model(self) -> None:
        import src.providers.llm as llm_mod
        llm_mod._dotenv_loaded = True

        with patch.dict(os.environ, {"LLM_BASE_URL": "https://test.com/v1"}, clear=True):
            with pytest.raises(RuntimeError, match="LLM_MODEL_NAME"):
                build_llm()


class TestReasoningEffortPassthrough:
    """LLM_REASONING_EFFORT is forwarded as extra_body.reasoning.effort."""

    def _capture(self, env: dict[str, str]) -> dict:
        import src.providers.llm as llm_mod
        llm_mod._dotenv_loaded = True

        captured: dict = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        with patch.dict(os.environ, env, clear=True):
            with patch.object(llm_mod, "ChatOpenAIWithReasoning", _FakeChatOpenAI):
                build_llm()
        return captured

    def test_effort_unset(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
            "LLM_API_KEY": "sk-test",
            "LLM_MODEL_NAME": "gpt-4",
        })
        assert "extra_body" not in captured

    def test_effort_medium(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
            "LLM_API_KEY": "or-test",
            "LLM_MODEL_NAME": "moonshotai/kimi-k2-thinking",
            "LLM_REASONING_EFFORT": "medium",
        })
        assert captured["extra_body"] == {"reasoning": {"effort": "medium"}}

    def test_effort_case_insensitive(self) -> None:
        captured = self._capture({
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
            "LLM_API_KEY": "or-test",
            "LLM_MODEL_NAME": "moonshotai/kimi-k2-thinking",
            "LLM_REASONING_EFFORT": "HIGH",
        })
        assert captured["extra_body"]["reasoning"]["effort"] == "high"


class TestExtractBalancedJson:
    def test_simple_json(self) -> None:
        result = _extract_balanced_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self) -> None:
        text = 'Here is the config: {"a": 1, "b": 2} and some more text.'
        result = _extract_balanced_json(text)
        assert result == {"a": 1, "b": 2}

    def test_nested_json(self) -> None:
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = _extract_balanced_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_escaped_quotes(self) -> None:
        text = r'{"msg": "he said \"hello\""}'
        result = _extract_balanced_json(text)
        assert result is not None
        assert "hello" in result["msg"]

    def test_no_json(self) -> None:
        assert _extract_balanced_json("no json here") is None

    def test_empty_string(self) -> None:
        assert _extract_balanced_json("") is None

    def test_braces_in_strings(self) -> None:
        text = '{"pattern": "if (x > 0) { return x; }"}'
        result = _extract_balanced_json(text)
        assert result is not None
        assert "return x" in result["pattern"]

    def test_multiple_objects_returns_first(self) -> None:
        text = '{"a": 1} {"b": 2}'
        result = _extract_balanced_json(text)
        assert result == {"a": 1}
