# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run all tests (excludes slow e2e backtests)
pytest --ignore=agent/tests/e2e_backtest --tb=short -q

# Run a single test file
pytest agent/tests/test_metrics.py --tb=short -q

# Run a single test function
pytest agent/tests/test_metrics.py::test_sharpe_ratio --tb=short -q

# Syntax check key modules
cd agent && python -m py_compile cli.py && python -m py_compile api_server.py && python -m py_compile mcp_server.py

# Lint
ruff check agent/ --fix

# Frontend
cd frontend && npm install && npm run dev        # dev server on :5899 (hot reload)
cd frontend && npm run build                      # production build → frontend/dist/

# Backend API server
vibe-trading serve --port 8899                    # production
python api_server.py --reload                     # dev mode, auto-reload on code changes
python api_server.py --reload --dev               # dev mode + auto-start Vite dev server

# MCP server (stdio)
vibe-trading-mcp

# Local dev (both hot reload)
# Terminal 1: cd agent && python api_server.py --reload          → API on :8899
# Terminal 2: cd frontend && npm run dev                         → UI on :5899
# Or single command: python api_server.py --reload --dev
# Browser: http://localhost:5899
```

## Architecture

**Entry points** (all in `agent/`):
- `cli.py` — Interactive TUI + CLI subcommands (`run`, `serve`, `--swarm-run`, etc.)
- `api_server.py` — FastAPI server (runs, sessions, upload, swarm, SSE, settings)
- `mcp_server.py` — MCP server exposing 22 tools over stdio/SSE

**Agent core** (`agent/src/agent/`):
- `loop.py` — ReAct loop with 5-layer context compression and parallel read/write tool batching
- `context.py` — System prompt builder with auto-recall from persistent memory
- `skills.py` — Skill loader (74 bundled SKILL.md files + user-created via CRUD)
- `tools.py` — `BaseTool` ABC + `ToolRegistry` (auto-discovers tools from `src/tools/`)
- `memory.py` — Lightweight workspace state per run
- `trace.py` — Execution trace writer

**Tools** (`agent/src/tools/`): 21 auto-discovered agent tools. Each subclasses `BaseTool` and implements `execute()`. Tools self-register when imported — adding a new tool means creating a class that inherits `BaseTool` with `name`, `description`, `parameters`, and `execute()`.

**Skills** (`agent/src/skills/`): 74 finance skill directories, each containing a `SKILL.md` with YAML frontmatter. Categories: data-source, strategy, analysis, asset-class, crypto, flow, tool.

**Backtest** (`agent/backtest/`):
- `engines/` — 7 market engines (ChinaA, GlobalEquity, Crypto, ChinaFutures, GlobalFutures, Forex, options_portfolio) + composite cross-market engine. All extend `base.py`.
- `loaders/` — 6 data sources (tushare, okx, yfinance, akshare, ccxt, futu). Each implements the `DataLoader` Protocol and registers via `@register` decorator in `registry.py`. Fallback chains resolve automatically per market.
- `optimizers/` — MVO, equal vol, max diversification, risk parity
- `runner.py` — Orchestrates engine selection, data loading, and execution

**Swarm** (`agent/src/swarm/`): DAG-based multi-agent orchestration. Presets are YAML files in `swarm/presets/` defining agents, roles, and workflow edges.

**Session** (`agent/src/session/`): Multi-turn chat with FTS5 session search.

**Memory** (`agent/src/memory/`): Cross-session persistent memory stored in `~/.vibe-trading/memory/`.

**Providers** (`agent/src/providers/`): LLM abstraction layer. `llm.py` provides `build_llm()` which reads `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` from `.env` environment variables (global, not per-user). Works with any OpenAI-compatible API (OpenRouter, DeepSeek, Gemini, Groq, DashScope, Zhipu, Moonshot, MiniMax, Ollama, etc). `chat.py` defines `ChatLLM` (raw message interface with function calling).

**Frontend** (`frontend/`): React 19 + Vite + TypeScript + Tailwind + Zustand + ECharts. Dev server on :5899, proxies API to :8899. Production: FastAPI serves `frontend/dist/` as static files.

## Code Conventions

- **Python**: Google-style docstrings, type hints encouraged, target Python 3.11+
- **Ruff**: E/F/W rules, line length 120, E501 ignored
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`)
- **OKX pairs**: `BTC-USDT` format (hyphen, uppercase)
- **UI text**: English. LLM output follows user language
- **File size**: aim for < 400 lines, max 800
- **Config**: via `.env`, YAML, or constants — no hardcoding
- **Package name**: PyPI package is `vibe-trading-ai`; CLI commands are `vibe-trading`, `vibe-trading-mcp`

## Git Flow & Versioning

**Branch model** (`feature → develop → release → main`):

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | Production | PR + review, only accepts release PRs |
| `release` | UAT testing | PR + review, only accepts develop PRs |
| `develop` | Development integration | PR + review |
| `feature/*`, `fix/*` | Individual features | None |

**Version management**: bump-my-version (configured in pyproject.toml)
```bash
bump-my-version bump patch    # 0.1.7 → 0.1.8
bump-my-version bump minor    # 0.1.7 → 0.2.0
bump-my-version bump major    # 0.1.7 → 1.0.0
```
Automatically updates pyproject.toml + frontend/package.json, commits, and creates git tag.

**CI/CD flow** (image built once, shared across UAT and Prod):
1. `feat/*` → PR → `develop`: CI lint + test (no build)
2. `develop` → PR → `release`: CI lint + test + build image (sha-*) + auto deploy UAT
3. UAT manual verification (fail → fix in feat → re-flow)
4. `release` → PR → `main`: code lands, no build
5. On `main`: `bump-my-version` → `git push --follow-tags` → CI retags sha-* image as v* (crane, no rebuild)
6. Manual Deploy Prod → approval → deploy → auto GitHub Release

**Image tags**: `develop-sha-{7-char}` (develop builds), `release-sha-{7-char}` (release builds), `vX.Y.Z` (retagged for prod)

## Environment

Copy `.env.example` to `.env` and set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL_NAME`. `TUSHARE_TOKEN` is optional (AKShare is the free fallback for A-shares).

## Key Patterns

- **Tool auto-discovery**: Tools in `agent/src/tools/` are auto-imported and registered. Add a new `BaseTool` subclass = new tool available.
- **Loader auto-registration**: Data loaders use `@register` decorator. `registry.py` lazily imports all loader modules and resolves per-market fallback chains.
- **5-layer compression**: The agent loop uses microcompact → context collapse → LLM summary → compact tool → iterative update to manage long conversations.
- **Skill frontmatter**: Each skill has YAML frontmatter (`name`, `description`, `category`) parsed by `frontmatter.py`.
- **Security boundaries**: API auth via JWT tokens, shell tools gated by entry point, file/upload roots restricted, path containment enforced. LLM and data source configuration via global `.env` environment variables (not per-user).
