from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cli


class TestCliInit:
    def test_render_env_content(self) -> None:
        content = cli._render_env_content(
            {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_API_KEY": "sk-or-test",
                "LLM_MODEL_NAME": "deepseek/deepseek-v3.2",
                "LLM_TEMPERATURE": "0.0",
                "LLM_TIMEOUT": "120",
                "LLM_MAX_RETRIES": "2",
                "TUSHARE_TOKEN": "ts-token",
            }
        )

        assert "LLM_BASE_URL=https://openrouter.ai/api/v1" in content
        assert "LLM_API_KEY=sk-or-test" in content
        assert "LLM_MODEL_NAME=deepseek/deepseek-v3.2" in content
        assert "TUSHARE_TOKEN=ts-token" in content
        assert "LLM_TIMEOUT=120" in content
        assert "LLM_MAX_RETRIES=2" in content

    def test_render_env_skips_empty(self) -> None:
        content = cli._render_env_content(
            {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL_NAME": "deepseek/deepseek-v3.2",
            }
        )
        assert "LLM_API_KEY" not in content
        assert "LLM_BASE_URL=https://openrouter.ai/api/v1" in content

    def test_cmd_init_writes_env(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"

        with patch.object(cli, "_INIT_ENV_PATH", env_path), \
             patch.object(
                 cli.Prompt,
                 "ask",
                 side_effect=[
                     "https://openrouter.ai/api/v1",
                     "sk-or-test-key",
                     "deepseek/deepseek-v3.2",
                     "ts-token",
                 ],
             ), \
             patch.object(cli.Confirm, "ask", return_value=True):
            result = cli.cmd_init()

        assert result == 0
        content = env_path.read_text(encoding="utf-8")
        assert "LLM_BASE_URL=https://openrouter.ai/api/v1" in content
        assert "LLM_API_KEY=sk-or-test-key" in content
        assert "LLM_MODEL_NAME=deepseek/deepseek-v3.2" in content
        assert "TUSHARE_TOKEN=ts-token" in content

    def test_cmd_init_local_no_key(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"

        with patch.object(cli, "_INIT_ENV_PATH", env_path), \
             patch.object(
                 cli.Prompt,
                 "ask",
                 side_effect=[
                     "http://localhost:11434/v1",
                     "",
                     "qwen2.5:32b",
                     "",
                 ],
             ), \
             patch.object(cli.Confirm, "ask", return_value=True):
            result = cli.cmd_init()

        assert result == 0
        content = env_path.read_text(encoding="utf-8")
        assert "LLM_BASE_URL=http://localhost:11434/v1" in content
        assert "LLM_MODEL_NAME=qwen2.5:32b" in content
        assert "LLM_API_KEY=" not in content
