"""Unified datasources layer — 13 Agent-facing get_* interfaces.

Usage::

    from src.datasources import get_kline, get_valuation, get_stock_news
"""

from .fundamental import get_f10, get_financial_snapshot, get_financial_statements, get_industry
from .market import get_kline, get_quote, get_quotes
from .news import get_flash_news, get_news_digest, get_stock_news
from .research import get_consensus_eps, get_research_reports
from .valuation import get_valuation, get_valuation_history

__all__ = [
    # Market (3)
    "get_kline",
    "get_quote",
    "get_quotes",
    # Valuation (2)
    "get_valuation",
    "get_valuation_history",
    # Fundamental (4)
    "get_financial_snapshot",
    "get_financial_statements",
    "get_f10",
    "get_industry",
    # News (3)
    "get_flash_news",
    "get_stock_news",
    "get_news_digest",
    # Research (2)
    "get_consensus_eps",
    "get_research_reports",
]
