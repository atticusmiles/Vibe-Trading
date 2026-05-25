"""Read URL content via direct HTTP fetch with HTML-to-Markdown conversion.

Mirrors the mcp-searxng web_url_read tool behavior: fetches a URL,
converts HTML to Markdown, and supports content extraction options.
"""

from __future__ import annotations

import json
import re
from typing import Any

import html2text
import httpx
from bs4 import BeautifulSoup

from src.agent.tools import BaseTool

_TIMEOUT = 30
_MAX_LENGTH_DEFAULT = 10000


class SearXNGUrlReaderTool(BaseTool):
    """Read a URL and convert HTML content to clean Markdown."""

    name = "read_url"

    @classmethod
    def check_available(cls) -> bool:
        return True

    description = (
        "Read a URL and convert its content to clean Markdown text. "
        "Supports content extraction by section heading, paragraph range, "
        "and character offset. Use this after web_search to read full content "
        "from interesting URLs."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch and read",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum number of characters to return (default 10000, max 50000)",
                "default": 10000,
            },
            "section": {
                "type": "string",
                "description": "Extract content under a specific heading (case-insensitive match)",
            },
            "paragraph_range": {
                "type": "string",
                "description": "Return specific paragraph ranges, e.g. '1-5', '3', '10-'",
            },
        },
        "required": ["url"],
    }
    repeatable = True

    @staticmethod
    def _extract_section(markdown: str, section_heading: str) -> str:
        """Extract content under a specific heading."""
        lines = markdown.split("\n")
        pattern = re.compile(rf"^#{{1,6}}\s*.*{re.escape(section_heading)}.*$", re.IGNORECASE)
        start_idx = -1
        current_level = 0
        for i, line in enumerate(lines):
            if pattern.match(line.strip()):
                start_idx = i
                match = re.match(r"^(#+)", line.strip())
                current_level = len(match.group(1)) if match else 0
                break
        if start_idx == -1:
            return ""
        end_idx = len(lines)
        for i in range(start_idx + 1, len(lines)):
            match = re.match(r"^(#+)", lines[i].strip())
            if match and len(match.group(1)) <= current_level:
                end_idx = i
                break
        return "\n".join(lines[start_idx:end_idx])

    @staticmethod
    def _extract_paragraph_range(markdown: str, range_str: str) -> str:
        """Extract a range of paragraphs."""
        paragraphs = [p for p in markdown.split("\n\n") if p.strip()]
        m = re.match(r"^(\d+)(?:-(\d*))?$", range_str)
        if not m:
            return ""
        start = int(m.group(1)) - 1
        end_str = m.group(2)
        if start < 0 or start >= len(paragraphs):
            return ""
        if end_str is None:
            return paragraphs[start]
        elif end_str == "":
            return "\n\n".join(paragraphs[start:])
        else:
            return "\n\n".join(paragraphs[start:int(end_str)])

    def execute(self, **kwargs: Any) -> str:
        url = kwargs["url"]
        max_length = min(int(kwargs.get("max_length", _MAX_LENGTH_DEFAULT)), 50000)
        section = kwargs.get("section")
        paragraph_range = kwargs.get("paragraph_range")

        try:
            with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/125.0.0.0 Safari/537.36"
                        ),
                    },
                )
                resp.raise_for_status()
                html = resp.text

            if not html or not html.strip():
                return json.dumps(
                    {"status": "error", "error": "Empty content from URL"},
                    ensure_ascii=False,
                )

            # Convert HTML to Markdown
            converter = html2text.HTML2Text()
            converter.body_width = 0  # no line wrapping
            converter.ignore_links = False
            converter.ignore_images = True
            converter.ignore_tables = False
            converter.body_width = 0
            converter.skip_internal_links = False
            converter.protect_links = True
            markdown = converter.handle(html)

            # Clean up excessive whitespace
            markdown = re.sub(r"\n{4,}", "\n\n\n", markdown).strip()

            # Apply section extraction
            if section:
                markdown = self._extract_section(markdown, section)
                if not markdown:
                    return json.dumps(
                        {"status": "ok", "url": url, "content": f"Section '{section}' not found in the content."},
                        ensure_ascii=False,
                    )

            # Apply paragraph range
            if paragraph_range:
                markdown = self._extract_paragraph_range(markdown, paragraph_range)
                if not markdown:
                    return json.dumps(
                        {"status": "ok", "url": url, "content": f"Paragraph range '{paragraph_range}' is invalid or out of bounds."},
                        ensure_ascii=False,
                    )

            # Truncate by character length
            if len(markdown) > max_length:
                markdown = markdown[:max_length] + "\n\n... (truncated)"

            return json.dumps(
                {"status": "ok", "url": url, "content": markdown, "length": len(markdown)},
                ensure_ascii=False,
            )

        except httpx.TimeoutException:
            return json.dumps(
                {"status": "error", "error": f"Request timed out after {_TIMEOUT}s"},
                ensure_ascii=False,
            )
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {"status": "error", "error": f"HTTP {exc.response.status_code}"},
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
            )
