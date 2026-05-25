"""LLM factory and JSON extraction helpers."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore


if ChatOpenAI is not None:
    class ChatOpenAIWithReasoning(ChatOpenAI):  # type: ignore[misc,valid-type]
        """ChatOpenAI that preserves provider reasoning across invoke + stream.

        langchain-openai 0.3.x drops non-standard fields in three paths:
          * _convert_dict_to_message — invoke / ainvoke (inbound)
          * _convert_delta_to_message_chunk — stream / astream (inbound)
          * _convert_message_to_dict — request serialization (outbound)
        Moonshot/DeepSeek emit `reasoning_content`; OpenRouter relays as
        `reasoning`. Inbound paths normalize to additional_kwargs["reasoning_content"];
        outbound path re-injects it so strict providers (kimi-k2.5) accept
        multi-turn continuations.
        """

        @staticmethod
        def _capture(src: Any, msg: Any) -> None:
            if value := src.get("reasoning_content") or src.get("reasoning"):
                msg.additional_kwargs["reasoning_content"] = value

        def _create_chat_result(self, response, generation_info=None):  # type: ignore[override]
            result = super()._create_chat_result(response, generation_info)
            raw = response if isinstance(response, dict) else response.model_dump()
            for gen, choice in zip(result.generations, raw["choices"]):
                self._capture(choice["message"], gen.message)
            return result

        def _convert_chunk_to_generation_chunk(  # type: ignore[override]
            self,
            chunk: dict,
            default_chunk_class: type,
            base_generation_info: Optional[dict],
        ):
            gen = super()._convert_chunk_to_generation_chunk(
                chunk, default_chunk_class, base_generation_info
            )
            if gen is None:
                return None
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices")
            if choices:
                self._capture(choices[0]["delta"], gen.message)
            return gen

        def _get_request_payload(  # type: ignore[override]
            self,
            input_: Any,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
        ) -> dict:
            """Re-inject reasoning_content and normalize assistant content.

            LangChain strips ``reasoning_content`` when serializing AIMessages
            back to OpenAI wire format. Moonshot kimi-k2.5 also rejects
            assistant turns where ``content`` is null or ``reasoning_content``
            is absent, breaking ReAct continuations after a tool call (#39).
            """
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            messages = super()._convert_input(input_).to_messages()
            for i, m in enumerate(payload["messages"]):
                if m.get("role") != "assistant":
                    continue
                if m.get("content") is None:
                    m["content"] = ""
                m["reasoning_content"] = messages[i].additional_kwargs.get("reasoning_content", "")
            return payload
else:
    ChatOpenAIWithReasoning = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# .env search order: $DATA_DIR/.env → project_root/.env → $CWD/.env
from src.core.config import get_data_dir
_ENV_CANDIDATES = [
    get_data_dir() / ".env",
    PROJECT_ROOT / ".env",
    Path.cwd() / ".env",
]

_dotenv_loaded: bool = False


def _load_env_file(path: Path) -> None:
    """Load a single .env file into os.environ (setdefault, no override)."""
    if load_dotenv is not None:
        load_dotenv(dotenv_path=path, override=True)
    else:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                os.environ[key] = value.strip().strip('"').strip("'")


def _ensure_dotenv() -> None:
    """Load `.env` from the first found candidate path."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    for candidate in _ENV_CANDIDATES:
        if candidate.exists():
            _load_env_file(candidate)
            break
    _dotenv_loaded = True


def build_llm(*, model_name: Optional[str] = None, callbacks: Any = None) -> Any:
    """Construct a ChatOpenAI instance from environment variables.

    Reads LLM config from .env / os.environ (global config, not per-user).
    Only three env vars needed: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME.

    Args:
        model_name: Model name override.
        callbacks: Optional LangChain callbacks.

    Returns:
        ChatOpenAI instance.

    Raises:
        RuntimeError: If no LLM config found.
    """
    _ensure_dotenv()

    name = model_name or os.getenv("LLM_MODEL_NAME", "")
    if not name:
        raise RuntimeError("Model name not configured (set LLM_MODEL_NAME in .env)")
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    timeout = int(os.getenv("LLM_TIMEOUT", "120"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
    effort = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()

    if ChatOpenAI is None:
        raise RuntimeError("langchain-openai is not installed")

    if temperature <= 0.0:
        temperature = 0.01

    kwargs: dict[str, Any] = dict(
        model=name,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        callbacks=callbacks,
    )
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    if effort:
        kwargs["extra_body"] = {"reasoning": {"effort": effort}}

    return ChatOpenAIWithReasoning(**kwargs)


def _extract_balanced_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract the outermost JSON object from text using bracket balancing.

    Args:
        text: Text that may embed a JSON object.

    Returns:
        Parsed dict, or None on failure.
    """
    start = -1
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
    return None
