"""manage_candidates tool: add or update research candidates.

Scanner agents use action="add" to batch-insert candidates.
Researcher/pro/con/manager agents use action="update" to write reports, extra_reports, or decisions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.agent.tools import BaseTool

_ALLOWED_STATUS = {"proposed", "passed"}


class ManageCandidatesTool(BaseTool):
    name = "manage_candidates"
    description = (
        "Manage research candidates. "
        "action='add': batch-insert new candidates (scanner use). "
        "action='update': update report, extra_report, status, or conclusion for a candidate."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "update"],
                "description": "'add' to insert candidates, 'update' to modify an existing candidate.",
            },
            "target_type": {
                "type": "string",
                "description": "trend / industry / stock",
            },
            "target_name": {
                "type": "string",
                "description": "Candidate name (required for update, optional for add).",
            },
            "candidates": {
                "type": "string",
                "description": 'JSON array [{name, code?, score?, reason?}] (required for add action).',
            },
            "report": {
                "type": "string",
                "description": "Markdown research report to write (update action).",
            },
            "report_type": {
                "type": "string",
                "description": "Report type: macro_analysis / industry_deep_dive / tech_analysis.",
            },
            "extra_report": {
                "type": "string",
                "description": 'JSON object {agent_id, title, content} to append to extra_reports.',
            },
            "status": {
                "type": "string",
                "enum": ["proposed", "passed"],
                "description": "New status — only proposed/passed allowed (researching is set by API).",
            },
            "conclusion": {
                "type": "string",
                "description": "Decision reason (used with status change).",
            },
        },
        "required": ["action", "target_type"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        target_type = kwargs["target_type"]
        try:
            if action == "add":
                return self._add(target_type, kwargs)
            if action == "update":
                return self._update(target_type, kwargs)
            return _err(f"Unknown action: {action}")
        except Exception as exc:
            return _err(str(exc))

    def _add(self, target_type: str, kwargs: dict[str, Any]) -> str:
        raw = kwargs.get("candidates", "[]")
        try:
            candidates = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            return _err(f"Invalid candidates JSON: {exc}")

        run_id = kwargs.get("_run_id", "")
        inserted = 0
        skipped = 0

        from src.db.database import get_db

        with get_db() as conn:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for c in candidates:
                name = c.get("name", "").strip()
                if not name:
                    continue
                # Per-day dedup: skip if same target_type+name already exists today
                existing = conn.execute(
                    "SELECT 1 FROM research_candidates "
                    "WHERE target_type = ? AND name = ? AND created_at >= ?",
                    (target_type, name, today),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                code = c.get("code")
                score = c.get("score", 0)
                reason = c.get("reason", "")
                try:
                    conn.execute(
                        "INSERT INTO research_candidates "
                        "(target_type, name, code, source_context, initial_score, status, source_run_id) "
                        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                        (target_type, name, code, reason, score, run_id),
                    )
                    inserted += 1
                except Exception:
                    skipped += 1

        return json.dumps(
            {"status": "ok", "action": "add", "target_type": target_type,
             "inserted": inserted, "skipped": skipped},
            ensure_ascii=False,
        )

    def _update(self, target_type: str, kwargs: dict[str, Any]) -> str:
        name = kwargs.get("target_name", "").strip()
        if not name:
            return _err("target_name is required for update action")

        from src.db.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT id, extra_reports FROM research_candidates "
                "WHERE target_type = ? AND name = ? ORDER BY created_at DESC LIMIT 1",
                (target_type, name),
            ).fetchone()
            if not row:
                return _err(f"Candidate not found: {target_type}/{name}")

            cid = row["id"]
            extra_reports = json.loads(row["extra_reports"] or "[]")
            updates: list[str] = []
            params: list[Any] = []

            if kwargs.get("report"):
                updates.append("report = ?")
                params.append(kwargs["report"])
                updates.append("report_type = ?")
                params.append(kwargs.get("report_type", ""))
                updates.append("reported_at = ?")
                params.append(datetime.now(timezone.utc).isoformat())

            if kwargs.get("extra_report"):
                try:
                    entry = json.loads(kwargs["extra_report"]) if isinstance(kwargs["extra_report"], str) else kwargs["extra_report"]
                except json.JSONDecodeError:
                    return _err("Invalid extra_report JSON")
                extra_reports.append(entry)
                updates.append("extra_reports = ?")
                params.append(json.dumps(extra_reports, ensure_ascii=False))

            status = kwargs.get("status")
            if status:
                if status not in _ALLOWED_STATUS:
                    return _err(f"Status '{status}' not allowed. Use: {_ALLOWED_STATUS}")
                updates.append("status = ?")
                params.append(status)

            if kwargs.get("conclusion"):
                updates.append("conclusion = ?")
                params.append(kwargs["conclusion"])

            if not updates:
                return _err("Nothing to update — provide report, extra_report, status, or conclusion")

            updates.append("updated_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
            params.append(cid)
            conn.execute(
                f"UPDATE research_candidates SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        result = {"status": "ok", "action": "update", "target_type": target_type,
                  "name": name, "fields_updated": len(updates) - 1}

        # Event trigger: when status becomes 'proposed', fire downstream scans
        if status == "proposed" and target_type in ("trend", "industry"):
            try:
                from src.scheduler.events import check_event_triggers
                triggered = check_event_triggers(target_type, name)
                if triggered:
                    result["triggered_runs"] = triggered
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Event trigger failed for %s/%s", target_type, name, exc_info=True,
                )

        return json.dumps(result, ensure_ascii=False)


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
