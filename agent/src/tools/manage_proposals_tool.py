"""manage_proposals tool: create or cancel proposals for fact-table changes.

Agents use action="create" to propose changes to trends/industries/stocks.
Agents use action="cancel" to withdraw their own pending proposals.
Adopt/reject is reserved for human users via the API.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.agent.tools import BaseTool

_ACTION_CREATE_FIELDS = {"title", "summary", "confidence", "payload", "run_id", "source_agent"}


class ManageProposalsTool(BaseTool):
    name = "manage_proposals"
    description = (
        "Manage proposals for fact-table (trend/industry/stock) changes. "
        "action='create': propose a new change (create/update/delete a fact record). "
        "action='cancel': withdraw a pending proposal by ID."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "cancel"],
                "description": "'create' to submit a proposal, 'cancel' to withdraw one.",
            },
            "target_type": {
                "type": "string",
                "description": "trend / industry / stock (required for create).",
            },
            "target_id": {
                "type": "integer",
                "description": "Fact-table row ID (required for update/delete proposals).",
            },
            "proposal_action": {
                "type": "string",
                "enum": ["create", "update", "delete"],
                "description": "Type of change being proposed: create new, update existing, or delete.",
            },
            "title": {
                "type": "string",
                "description": "Short title for the proposal.",
            },
            "summary": {
                "type": "string",
                "description": "Detailed reasoning for the proposed change.",
            },
            "confidence": {
                "type": "integer",
                "description": "Confidence score 0-10 (default: 5).",
            },
            "payload": {
                "type": "string",
                "description": 'JSON string with fields to apply (e.g. \'{"confidence":7,"evidence":"..."}\').',
            },
            "proposal_id": {
                "type": "integer",
                "description": "Proposal ID to cancel (required for cancel action).",
            },
        },
        "required": ["action"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        try:
            if action == "create":
                return self._create(kwargs)
            if action == "cancel":
                return self._cancel(kwargs)
            return _err(f"Unknown action: {action}")
        except Exception as exc:
            return _err(str(exc))

    def _create(self, kwargs: dict[str, Any]) -> str:
        target_type = kwargs.get("target_type", "")
        if target_type not in ("trend", "industry", "stock"):
            return _err("target_type must be trend, industry, or stock")

        proposal_action = kwargs.get("proposal_action")
        if proposal_action not in ("create", "update", "delete"):
            return _err("proposal_action must be create, update, or delete")

        title = kwargs.get("title", "").strip()
        if not title:
            return _err("title is required")

        payload = kwargs.get("payload", "{}")
        if isinstance(payload, dict):
            payload = json.dumps(payload, ensure_ascii=False)

        try:
            json.loads(payload)
        except json.JSONDecodeError:
            return _err("payload must be valid JSON")

        target_id = kwargs.get("target_id")
        if proposal_action in ("update", "delete") and not target_id:
            return _err(f"target_id is required for {proposal_action} proposals")

        confidence = kwargs.get("confidence", 5)
        summary = kwargs.get("summary", "")
        run_id = kwargs.get("_run_id", "")
        source_agent = kwargs.get("source_agent", "")
        user_id = _parse_int(kwargs.get("_user_id"))
        if not user_id:
            return _err("_user_id is required")

        from src.db.database import get_db

        with get_db() as conn:
            # For create proposals: validate payload has content
            if proposal_action == "create":
                payload_data = json.loads(payload)
                if not payload_data:
                    return _err("payload has no valid fields for create action")

            # For update proposals: snapshot original state
            original_payload = None
            if proposal_action == "update":
                table_map = {"trend": "trends", "industry": "industries", "stock": "stocks"}
                table = table_map[target_type]
                current = conn.execute(
                    f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
                    (target_id, user_id),
                ).fetchone()
                if not current:
                    return _err(f"Target {target_type}/{target_id} not found")
                exclude = {"id", "user_id", "created_at", "updated_at"}
                original_payload = json.dumps(
                    {k: v for k, v in dict(current).items() if k not in exclude},
                    ensure_ascii=False,
                )

            # Check for existing pending proposal on same target
            if target_id and proposal_action in ("update", "delete"):
                existing = conn.execute(
                    "SELECT id, confidence FROM proposals "
                    "WHERE user_id = ? AND target_type = ? AND target_id = ? AND status = 'pending'",
                    (user_id, target_type, target_id),
                ).fetchone()
                if existing and confidence <= existing["confidence"]:
                    return _err(
                        f"Pending proposal #{existing['id']} already exists "
                        f"(confidence={existing['confidence']}). Raise confidence to replace."
                    )
                if existing:
                    conn.execute(
                        "UPDATE proposals SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(), existing["id"]),
                    )

            try:
                cursor = conn.execute(
                    "INSERT INTO proposals "
                    "(user_id, target_type, target_id, action, status, title, summary, confidence, "
                    "payload, original_payload, run_id, source_agent) "
                    "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id, target_type, target_id or 0, proposal_action,
                        title, summary, confidence,
                        payload, original_payload, run_id, source_agent,
                    ),
                )
            except Exception as exc:
                return _err(f"Failed to create proposal: {exc}")

            proposal_id = cursor.lastrowid

        return json.dumps(
            {"status": "ok", "action": "create", "proposal_id": proposal_id,
             "target_type": target_type, "proposal_action": proposal_action,
             "title": title},
            ensure_ascii=False,
        )

        return json.dumps(
            {"status": "ok", "action": "create", "proposal_id": proposal_id,
             "target_type": target_type, "proposal_action": proposal_action,
             "title": title},
            ensure_ascii=False,
        )

    def _cancel(self, kwargs: dict[str, Any]) -> str:
        proposal_id = kwargs.get("proposal_id")
        if not proposal_id:
            return _err("proposal_id is required for cancel action")

        source_agent = kwargs.get("source_agent", "")
        user_id = _parse_int(kwargs.get("_user_id"))
        if not user_id:
            return _err("_user_id is required")

        from src.db.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT id, status, source_agent FROM proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
            if not row:
                return _err(f"Proposal #{proposal_id} not found")
            if row["status"] != "pending":
                return _err(f"Proposal #{proposal_id} is {row['status']}, only pending can be cancelled")

            conn.execute(
                "UPDATE proposals SET status = 'cancelled', reviewed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), proposal_id),
            )

        return json.dumps(
            {"status": "ok", "action": "cancel", "proposal_id": proposal_id},
            ensure_ascii=False,
        )


def _parse_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().isdigit():
        return int(val)
    return 0


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
