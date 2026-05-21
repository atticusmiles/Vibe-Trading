"""Candidates API: query, detail, and batch-research endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.db import get_db
from .base import require_jwt, require_real_user

_VALID_TARGET_TYPES = {"trend", "industry", "stock"}
_PRESET_MAP = {
    "trend": "research_trends",
    "industry": "research_industries",
    "stock": "research_stocks",
}


class BatchResearchRequest(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    max_concurrent: int = Field(3, ge=1, le=10)


class CandidateResponse(BaseModel):
    id: int
    target_type: str
    name: str
    code: Optional[str] = None
    source_context: Optional[str] = None
    initial_score: int = 0
    status: str = "pending"
    source_run_id: Optional[str] = None
    research_run_id: Optional[str] = None
    report: Optional[str] = None
    report_type: Optional[str] = None
    reported_at: Optional[str] = None
    extra_reports: Optional[str] = "[]"
    conclusion: Optional[str] = None
    proposal_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
    page: int
    per_page: int


class BatchResearchResponse(BaseModel):
    runs: list[dict]
    total: int
    skipped: int


def _row_to_response(row: Any) -> CandidateResponse:
    return CandidateResponse(**dict(row))


def register_candidates_routes(app: FastAPI) -> None:

    @app.get("/api/research/candidates", response_model=CandidateListResponse)
    async def list_candidates(
        target_type: Optional[str] = Query(None),
        candidate_status: Optional[str] = Query(None, alias="status"),
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
        user_id: int = Depends(require_jwt),
    ):
        conditions = []
        params: list[Any] = []

        if target_type:
            if target_type not in _VALID_TARGET_TYPES:
                raise HTTPException(400, f"Invalid target_type: {target_type}")
            conditions.append("target_type = ?")
            params.append(target_type)

        if candidate_status:
            conditions.append("status = ?")
            params.append(candidate_status)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with get_db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM research_candidates {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM research_candidates {where} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()

        return CandidateListResponse(
            items=[_row_to_response(r) for r in rows],
            total=total, page=page, per_page=per_page,
        )

    @app.get("/api/research/candidates/{candidate_id}", response_model=CandidateResponse)
    async def get_candidate(candidate_id: int, user_id: int = Depends(require_jwt)):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM research_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Candidate not found")
        return _row_to_response(row)

    @app.post("/api/research/candidates/batch-research", response_model=BatchResearchResponse)
    async def batch_research(req: BatchResearchRequest, user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            placeholders = ",".join("?" * len(req.candidate_ids))
            rows = conn.execute(
                f"SELECT id, target_type, name, code, status, source_context, initial_score "
                f"FROM research_candidates WHERE id IN ({placeholders})",
                req.candidate_ids,
            ).fetchall()

        if not rows:
            raise HTTPException(400, "No candidates found")

        # Validate consistency
        target_types = {r["target_type"] for r in rows}
        if len(target_types) > 1:
            raise HTTPException(400, "All candidates must have the same target_type")

        target_type = target_types.pop()
        pending_rows = [r for r in rows if r["status"] == "pending"]
        if not pending_rows:
            raise HTTPException(400, "No pending candidates to research")

        preset_name = _PRESET_MAP.get(target_type)
        if not preset_name:
            raise HTTPException(400, f"No research preset for target_type: {target_type}")

        # Lazy-import to avoid circular deps at module load
        from src.swarm.runtime import SwarmRuntime
        from src.swarm.store import SwarmStore
        from src.core.config import get_swarm_dir
        from src.swarm.presets import load_preset

        swarm_dir = get_swarm_dir()
        store = SwarmStore(base_dir=swarm_dir)
        runtime = SwarmRuntime(store=store)

        # Load preset to check variables
        try:
            preset = load_preset(preset_name)
        except FileNotFoundError:
            raise HTTPException(500, f"Preset {preset_name} not found")

        runs = []
        skipped = len(rows) - len(pending_rows)

        for row in pending_rows:
            run_id = str(uuid.uuid4())

            # Atomically mark as researching
            with get_db() as conn:
                updated = conn.execute(
                    "UPDATE research_candidates SET status = 'researching', "
                    "research_run_id = ?, updated_at = datetime('now') "
                    "WHERE id = ? AND status = 'pending'",
                    (run_id, row["id"]),
                ).rowcount
                if not updated:
                    skipped += 1
                    continue

            # Build user_vars for this candidate
            candidate_info = json.dumps({
                "name": row["name"],
                "code": row["code"],
                "source_context": row["source_context"],
                "initial_score": row["initial_score"],
            }, ensure_ascii=False)

            user_vars = {
                "candidate_names": json.dumps([row["name"]], ensure_ascii=False),
                "candidate_info": candidate_info,
                "_run_id": run_id,
                "_user_id": str(user_id),
            }

            try:
                run = runtime.start_run(preset_name, user_vars)
                runs.append({
                    "run_id": run.id,
                    "candidate_id": row["id"],
                    "candidate_name": row["name"],
                    "status": run.status.value,
                })
            except Exception as exc:
                # Revert candidate status on failure
                with get_db() as conn:
                    conn.execute(
                        "UPDATE research_candidates SET status = 'pending', "
                        "research_run_id = NULL WHERE id = ?",
                        (row["id"],),
                    )
                runs.append({
                    "candidate_id": row["id"],
                    "candidate_name": row["name"],
                    "error": str(exc),
                })

        return BatchResearchResponse(runs=runs, total=len(runs), skipped=skipped)
