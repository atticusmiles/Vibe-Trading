"""Unified datasources layer — Agent-facing interfaces + news sync service."""

from .fundamental import get_f10, get_financial_snapshot, get_financial_statements, get_industry
from .market import get_kline, get_quote, get_quotes
from .news import (
    NewsSyncService,
    get_news_digest,
    get_recent_news,
    search_news,
    search_stock_news,
)
from .research import get_consensus_eps, get_research_reports
from .valuation import get_valuation, get_valuation_history, get_valuation_percentile

__all__ = [
    # Market (3)
    "get_kline",
    "get_quote",
    "get_quotes",
    # Valuation (3)
    "get_valuation",
    "get_valuation_history",
    "get_valuation_percentile",
    # Fundamental (4)
    "get_financial_snapshot",
    "get_financial_statements",
    "get_f10",
    "get_industry",
    # News (4 + sync)
    "get_recent_news",
    "search_stock_news",
    "get_news_digest",
    "search_news",
    "NewsSyncService",
    # Research (2)
    "get_consensus_eps",
    "get_research_reports",
]
