"""Event-driven triggers for the research engine.

When a candidate's status changes to 'proposed', check if downstream
scans should be triggered automatically.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def check_event_triggers(target_type: str, candidate_name: str) -> list[str]:
    """Check and fire event-driven triggers when a candidate becomes proposed.

    Args:
        target_type: The candidate's target type (trend/industry/stock).
        candidate_name: The candidate's name.

    Returns:
        List of run IDs that were started.
    """
    runs: list[str] = []

    if target_type == "trend":
        run_id = _trigger_scan_industries(candidate_name)
        if run_id:
            runs.append(run_id)

    elif target_type == "industry":
        run_id = _trigger_scan_stocks(candidate_name)
        if run_id:
            runs.append(run_id)

    return runs


def _trigger_scan_industries(trigger_trend: str) -> str | None:
    """Trigger scan_industries when a trend becomes proposed."""
    from . import _run_preset, _build_trend_context, _build_existing_list

    trend_ctx = _build_trend_context()
    existing = _build_existing_list("industry")

    logger.info("Event trigger: trend '%s' proposed → starting scan_industries", trigger_trend)
    return _run_preset("scan_industries", {
        "trend_context": trend_ctx,
        "existing_industries": existing,
        "existing_trends": _build_existing_list("trend"),
    })


def _trigger_scan_stocks(trigger_industry: str) -> str | None:
    """Trigger scan_stocks when an industry becomes proposed."""
    from . import _run_preset, _build_industry_details, _build_existing_list, _build_current_portfolio

    details = _build_industry_details()
    existing = _build_existing_list("stock")
    portfolio = _build_current_portfolio()

    logger.info("Event trigger: industry '%s' proposed → starting scan_stocks", trigger_industry)
    return _run_preset("scan_stocks", {
        "industry_names": trigger_industry,
        "industry_details": details,
        "existing_stocks": existing,
        "current_portfolio": portfolio,
    })
