"""Research modules: trends, industries, stocks, proposals, and dashboard."""

from __future__ import annotations


def register_all_routes(app) -> None:
    from .trends import register_routes as reg_trends
    from .industries import register_routes as reg_industries
    from .stocks import register_routes as reg_stocks
    from .proposals import register_proposal_routes as reg_proposals
    from .dashboard import register_routes as reg_dashboard
    reg_trends(app)
    reg_industries(app)
    reg_stocks(app)
    reg_proposals(app)
    reg_dashboard(app)
