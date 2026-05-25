"""Swarm DAG orchestration runtime.

Core orchestrator: schedules workers by topological layer, parallel within each
layer and serial between layers. Execution runs in a background daemon thread
with cancellation and event callback support.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from src.swarm.mailbox import Mailbox

SHANGHAI_TZ = timezone(timedelta(hours=8))
from src.swarm.models import (
    RunStatus,
    SwarmAgentSpec,
    SwarmEvent,
    SwarmRun,
    SwarmTask,
    TaskStatus,
    WorkerResult,
)
from src.swarm.presets import build_run_from_preset
from src.swarm.store import SwarmStore
from src.swarm.task_store import (
    TaskStore,
    resolve_dependencies,
    topological_layers,
    validate_dag,
)
from src.swarm.worker import run_worker

logger = logging.getLogger(__name__)


class SwarmRuntime:
    """Swarm DAG orchestration engine.

    Manages the full lifecycle of a swarm run: creation, scheduling, execution,
    and cancellation. Each run executes in an independent background daemon thread;
    tasks within a layer run in parallel via ThreadPoolExecutor.

    Attributes:
        _store: SwarmStore persistence layer.
        _max_workers: Maximum concurrent workers in ThreadPoolExecutor.
    """

    def __init__(self, store: SwarmStore, max_workers: int = 4) -> None:
        """Initialize SwarmRuntime.

        Args:
            store: SwarmStore instance for run persistence.
            max_workers: Maximum concurrent worker threads.
        """
        self._store = store
        self._max_workers = max_workers
        self._cancel_events: dict[str, threading.Event] = {}
        self._live_callbacks: dict[str, Callable] = {}
        self._lock = threading.Lock()

    def start_run(
        self,
        preset_name: str,
        user_vars: dict[str, str],
        live_callback: Callable | None = None,
        include_shell_tools: bool = False,
    ) -> SwarmRun:
        """Start a swarm run. Returns immediately, execution happens in background.

        Args:
            preset_name: YAML preset name to execute.
            user_vars: User-provided variables for prompt templates.
            live_callback: Optional callback invoked for each event in real-time.
            include_shell_tools: Whether workers may register shell tools.

        Returns:
            The created SwarmRun instance (status=pending initially).

        Raises:
            FileNotFoundError: If preset does not exist.
            ValueError: If DAG validation fails.
        """
        run = build_run_from_preset(preset_name, user_vars)
        validate_dag(run.tasks)
        self._store.create_run(run)

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[run.id] = cancel_event
            if live_callback is not None:
                self._live_callbacks[run.id] = live_callback

        thread = threading.Thread(
            target=self._execute_run,
            args=(run, cancel_event, include_shell_tools),
            name=f"swarm-{run.id}",
            daemon=True,
        )
        thread.start()

        return run

    def cancel_run(self, run_id: str) -> bool:
        """Signal cancellation for a running swarm.

        Args:
            run_id: ID of the run to cancel.

        Returns:
            True if cancellation was signalled, False if run not found.
        """
        with self._lock:
            cancel_event = self._cancel_events.get(run_id)
        if cancel_event is None:
            return False
        cancel_event.set()
        return True

    def _emit_event(self, run_id: str, event: SwarmEvent) -> None:
        """Persist an event and forward to live callback if registered.

        Args:
            run_id: Run identifier.
            event: Event to persist.
        """
        try:
            self._store.append_event(run_id, event)
        except Exception:
            logger.warning("Failed to persist event for run %s", run_id, exc_info=True)
        with self._lock:
            cb = self._live_callbacks.get(run_id)
        if cb is not None:
            try:
                cb(event)
            except Exception:
                logger.warning("Live callback failed for run %s", run_id, exc_info=True)

    def _make_event(
        self,
        event_type: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        data: dict | None = None,
    ) -> SwarmEvent:
        """Create a SwarmEvent with current timestamp.

        Args:
            event_type: Event type string.
            agent_id: Optional agent identifier.
            task_id: Optional task identifier.
            data: Optional additional data.

        Returns:
            SwarmEvent instance.
        """
        return SwarmEvent(
            type=event_type,
            agent_id=agent_id,
            task_id=task_id,
            data=data or {},
            timestamp=datetime.now(SHANGHAI_TZ).isoformat(),
        )

    _RUN_HARD_TIMEOUT_SECONDS = 1800  # 30 min — safety net for stuck workers

    def _execute_run(
        self,
        run: SwarmRun,
        cancel_event: threading.Event,
        include_shell_tools: bool = False,
    ) -> None:
        """Core orchestration loop (runs in background thread).

        Steps:
            1. Update run status to running
            2. Initialize TaskStore, save all tasks
            3. Compute topological layers
            4. For each layer:
               a. Check cancellation
               b. Submit all tasks to ThreadPoolExecutor
               c. Collect results, resolve dependencies, update store
            5. Update run status to completed/failed/cancelled

        A hard timeout (30 min) is enforced via threading.Timer. If the run
        exceeds this, the cancel event is set and the run is marked as failed.

        Args:
            run: SwarmRun to execute.
            cancel_event: Threading event for cancellation signalling.
            include_shell_tools: Whether workers may register shell tools.
        """
        run_id = run.id
        run_dir = self._store.run_dir(run_id)

        # Hard timeout: force-cancel if the run exceeds the global budget
        hard_timeout_fired = threading.Event()

        def _on_hard_timeout() -> None:
            hard_timeout_fired.set()
            cancel_event.set()
            logger.error("Run %s exceeded hard timeout of %ds — forcing cancel", run_id, self._RUN_HARD_TIMEOUT_SECONDS)

        hard_timer = threading.Timer(self._RUN_HARD_TIMEOUT_SECONDS, _on_hard_timeout)
        hard_timer.daemon = True
        hard_timer.start()

        try:
            # Mark as running
            run.status = RunStatus.running
            self._store.update_run(run)
            self._emit_event(run_id, self._make_event("run_started"))

            # Initialize task store
            task_store = TaskStore(run_dir)
            for task in run.tasks:
                task_store.save_task(task)

            # Build agent lookup
            agent_map: dict[str, SwarmAgentSpec] = {a.id: a for a in run.agents}

            # Compute execution layers
            layers = topological_layers(run.tasks)
            task_summaries: dict[str, str] = {}
            all_succeeded = True

            for layer_idx, layer_task_ids in enumerate(layers):
                # Check cancellation between layers
                if cancel_event.is_set():
                    logger.info("Run %s cancelled at layer %d", run_id, layer_idx)
                    self._cancel_remaining_tasks(task_store, layer_task_ids, run.tasks)
                    all_succeeded = False
                    break

                self._emit_event(
                    run_id,
                    self._make_event(
                        "layer_started",
                        data={"layer": layer_idx, "tasks": layer_task_ids},
                    ),
                )

                # Execute all tasks in this layer in parallel
                layer_results = self._execute_layer(
                    run=run,
                    task_store=task_store,
                    agent_map=agent_map,
                    layer_task_ids=layer_task_ids,
                    task_summaries=task_summaries,
                    run_dir=run_dir,
                    cancel_event=cancel_event,
                    include_shell_tools=include_shell_tools,
                )

                # Process results
                for tid, result in layer_results.items():
                    # Accumulate token counts to run totals
                    run.total_input_tokens += result.input_tokens
                    run.total_output_tokens += result.output_tokens

                    if result.status in ("completed", "timeout", "token_limit"):
                        task_summaries[tid] = result.summary
                        now_iso = datetime.now(SHANGHAI_TZ).isoformat()
                        task_store.update_status(
                            tid, TaskStatus.completed,
                            summary=result.summary,
                            completed_at=now_iso,
                            artifacts=result.artifact_paths,
                            worker_iterations=result.iterations,
                        )
                        resolve_dependencies(run_dir / "tasks", tid)
                        self._emit_event(
                            run_id,
                            self._make_event("task_completed", task_id=tid,
                                             data={"status": result.status,
                                                   "iterations": result.iterations,
                                                   "input_tokens": result.input_tokens,
                                                   "output_tokens": result.output_tokens}),
                        )
                    else:
                        all_succeeded = False
                        task_store.update_status(
                            tid, TaskStatus.failed,
                            error=result.error or "Unknown error",
                            completed_at=datetime.now(SHANGHAI_TZ).isoformat(),
                            worker_iterations=result.iterations,
                        )
                        self._emit_event(
                            run_id,
                            self._make_event("task_failed", task_id=tid,
                                             data={"error": result.error,
                                                   "input_tokens": result.input_tokens,
                                                   "output_tokens": result.output_tokens}),
                        )

        except Exception as exc:
            logger.error("Run %s failed with exception", run_id, exc_info=True)
            all_succeeded = False
            self._emit_event(
                run_id,
                self._make_event("run_error", data={"error": str(exc)}),
            )

        finally:
            hard_timer.cancel()

            # Finalize run
            if hard_timeout_fired.is_set():
                final_status = RunStatus.failed
                error_msg = f"Run exceeded hard timeout of {self._RUN_HARD_TIMEOUT_SECONDS}s"
                # Mark remaining incomplete tasks as cancelled
                for task in run.tasks:
                    if task.status not in (TaskStatus.completed, TaskStatus.failed):
                        try:
                            task_store.update_status(task.id, TaskStatus.cancelled, error=error_msg)
                        except Exception:
                            pass
            elif cancel_event.is_set():
                final_status = RunStatus.cancelled
            elif all_succeeded:
                final_status = RunStatus.completed
            else:
                final_status = RunStatus.failed

            run.status = final_status
            run.completed_at = datetime.now(SHANGHAI_TZ).isoformat()

            # Sync tasks back to run model
            try:
                run.tasks = task_store.load_all()
            except Exception:
                pass

            # Set final report from aggregation task (last task) if available
            if task_summaries:
                last_layer = layers[-1] if layers else []
                for tid in last_layer:
                    if tid in task_summaries:
                        run.final_report = task_summaries[tid]
                        break

            try:
                self._store.update_run(run)
            except Exception:
                logger.warning("Failed to persist final state for run %s", run_id, exc_info=True)

            self._emit_event(run_id, self._make_event("run_completed", data={"status": final_status.value}))

            # Sync candidate status: if the agent didn't update the candidate,
            # auto-resolve it based on the run outcome so it doesn't stay "researching" forever.
            self._sync_candidates_after_run(run_id, run, final_status)

            # Cleanup cancel event and live callback
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._live_callbacks.pop(run_id, None)

    def _sync_candidates_after_run(self, run_id: str, run: SwarmRun, final_status: RunStatus) -> None:
        """Auto-resolve candidate status after a swarm run completes.

        If the manager agent successfully called manage_candidates, the candidate
        is already 'proposed' or 'passed'. If not (still 'researching'), infer
        the outcome from proposals created during this run and update accordingly.
        """
        import json as _json
        from src.db.database import get_db as _get_db

        try:
            with _get_db() as conn:
                stuck = conn.execute(
                    "SELECT id, target_type, name FROM research_candidates "
                    "WHERE research_run_id = ? AND status = 'researching'",
                    (run_id,),
                ).fetchall()

            if not stuck:
                return

            for cand in stuck:
                if final_status in (RunStatus.completed,):
                    # Don't guess — if the manager didn't set a status, auto-pass
                    # so the candidate doesn't stay stuck in "researching".
                    with _get_db() as conn:
                        conn.execute(
                            "UPDATE research_candidates SET status = 'passed', "
                            "conclusion = 'Research completed but no proposal was created by the manager', "
                            "updated_at = datetime('now') WHERE id = ?",
                            (cand["id"],),
                        )
                    logger.info(
                        "Auto-passed candidate %s/%s (manager did not create a proposal, run %s)",
                        cand["target_type"], cand["name"], run_id,
                    )
                else:
                    # Run failed/cancelled — reset to pending for retry
                    with _get_db() as conn:
                        conn.execute(
                            "UPDATE research_candidates SET status = 'pending', "
                            "research_run_id = NULL, updated_at = datetime('now') WHERE id = ?",
                            (cand["id"],),
                        )
                    logger.info(
                        "Run %s %s — reset candidate %s/%s to pending",
                        run_id, final_status.value, cand["target_type"], cand["name"],
                    )

        except Exception:
            logger.warning("Failed to sync candidates after run %s", run_id, exc_info=True)

    def _execute_layer(
        self,
        run: SwarmRun,
        task_store: TaskStore,
        agent_map: dict[str, SwarmAgentSpec],
        layer_task_ids: list[str],
        task_summaries: dict[str, str],
        run_dir: Path,
        cancel_event: threading.Event,
        include_shell_tools: bool = False,
    ) -> dict[str, WorkerResult]:
        """Execute all tasks in a single layer in parallel, with retry on failure.

        Each task is retried up to agent_spec.max_retries times if the worker
        returns status="failed". A "task_retry" event is emitted before each retry.

        Args:
            run: The SwarmRun being executed.
            task_store: TaskStore for task persistence.
            agent_map: Agent specs keyed by agent_id.
            layer_task_ids: Task IDs in this layer.
            task_summaries: Accumulated task summaries from previous layers.
            run_dir: Run directory path.
            cancel_event: Cancellation event.
            include_shell_tools: Whether workers may register shell tools.

        Returns:
            Mapping of task_id -> WorkerResult for all tasks in this layer.
        """
        results: dict[str, WorkerResult] = {}

        def _event_callback(event: SwarmEvent) -> None:
            self._emit_event(run.id, event)

        # Manual executor lifecycle (not `with`) so KeyboardInterrupt and
        # the layer deadline don't block main on `shutdown(wait=True)` —
        # `wait=False + cancel_futures=True` lets pending work drop and
        # the CLI return immediately. Running workers finish naturally.
        executor = ThreadPoolExecutor(max_workers=self._max_workers)
        futures: dict[Future[WorkerResult], str] = {}
        layer_budget = 0  # seconds — max per-task (retries × timeout) across layer
        try:
            for tid in layer_task_ids:
                task = task_store.load_task(tid)
                agent_spec = agent_map.get(task.agent_id)
                if agent_spec is None:
                    results[tid] = WorkerResult(
                        status="failed", summary="",
                        error=f"Agent '{task.agent_id}' not found in preset",
                    )
                    continue

                # Mark task as in_progress
                task_store.update_status(
                    tid, TaskStatus.in_progress,
                    started_at=datetime.now(SHANGHAI_TZ).isoformat(),
                )
                self._emit_event(
                    run.id,
                    self._make_event("task_started", agent_id=agent_spec.id, task_id=tid),
                )

                # Build upstream summaries from input_from mapping
                upstream: dict[str, str] = {}
                for context_key, source_task_id in task.input_from.items():
                    if source_task_id in task_summaries:
                        upstream[context_key] = task_summaries[source_task_id]

                future = executor.submit(
                    self._run_worker_with_retries,
                    agent_spec=agent_spec,
                    task=task,
                    upstream_summaries=upstream,
                    user_vars=run.user_vars,
                    run_dir=run_dir,
                    event_callback=_event_callback,
                    run_id=run.id,
                    include_shell_tools=include_shell_tools,
                )
                futures[future] = tid
                per_task_budget = agent_spec.timeout_seconds * (agent_spec.max_retries + 1)
                layer_budget = max(layer_budget, per_task_budget)

            # Collect results with a hard layer-level deadline — defends against
            # worker threads stuck in C extensions / blocked I/O that bypass the
            # in-loop timeout check (issue #42).
            deadline_buffer = 60
            layer_deadline = layer_budget + deadline_buffer if layer_budget else None

            try:
                for future in as_completed(futures, timeout=layer_deadline):
                    tid = futures[future]
                    try:
                        results[tid] = future.result()
                    except Exception as exc:
                        logger.error("Worker for task %s raised exception", tid, exc_info=True)
                        results[tid] = WorkerResult(
                            status="failed", summary="",
                            error=str(exc),
                        )
            except FuturesTimeoutError:
                for pending, tid in futures.items():
                    if tid in results:
                        continue
                    pending.cancel()
                    logger.error(
                        "Worker for task %s exceeded layer deadline (%ds)",
                        tid, layer_deadline,
                    )
                    results[tid] = WorkerResult(
                        status="timeout", summary="",
                        error=f"Worker exceeded layer deadline of {layer_deadline}s",
                    )
        except KeyboardInterrupt:
            cancel_event.set()
            logger.warning("Swarm layer interrupted — cancelling pending workers")
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return results

    def _run_worker_with_retries(
        self,
        agent_spec: SwarmAgentSpec,
        task: SwarmTask,
        upstream_summaries: dict[str, str],
        user_vars: dict[str, str],
        run_dir: Path,
        event_callback: Callable[[SwarmEvent], None] | None,
        run_id: str,
        include_shell_tools: bool = False,
    ) -> WorkerResult:
        """Run a worker with automatic retry on failure.

        Retries up to agent_spec.max_retries times. Emits a "task_retry" event
        before each retry attempt. Token counts are accumulated across all
        attempts.

        Args:
            agent_spec: Agent role specification.
            task: The task to execute.
            upstream_summaries: Summaries from upstream tasks.
            user_vars: User-provided template variables.
            run_dir: Run directory path.
            event_callback: Optional event callback.
            run_id: Run identifier for event emission.
            include_shell_tools: Whether the worker may register shell tools.

        Returns:
            WorkerResult from the last attempt.
        """
        max_retries = agent_spec.max_retries
        cumulative_input_tokens = 0
        cumulative_output_tokens = 0
        result: WorkerResult | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                self._emit_event(
                    run_id,
                    self._make_event(
                        "task_retry",
                        agent_id=agent_spec.id,
                        task_id=task.id,
                        data={"attempt": attempt + 1, "max_retries": max_retries,
                              "previous_error": result.error if result else None},
                    ),
                )
                logger.info(
                    "Retrying task %s (attempt %d/%d)",
                    task.id, attempt + 1, max_retries + 1,
                )

            result = run_worker(
                agent_spec=agent_spec,
                task=task,
                upstream_summaries=upstream_summaries,
                user_vars=user_vars,
                run_dir=run_dir,
                event_callback=event_callback,
                include_shell_tools=include_shell_tools,
            )

            cumulative_input_tokens += result.input_tokens
            cumulative_output_tokens += result.output_tokens

            if result.status != "failed":
                # Success (or timeout/token_limit/completed) — no more retries
                result = result.model_copy(update={
                    "input_tokens": cumulative_input_tokens,
                    "output_tokens": cumulative_output_tokens,
                })
                return result

        # All retries exhausted, return the last failed result with cumulative tokens
        if result is not None:
            result = result.model_copy(update={
                "input_tokens": cumulative_input_tokens,
                "output_tokens": cumulative_output_tokens,
            })
        return result  # type: ignore[return-value]

    def _cancel_remaining_tasks(
        self,
        task_store: TaskStore,
        current_layer_ids: list[str],
        all_tasks: list[SwarmTask],
    ) -> None:
        """Mark all non-completed tasks as cancelled.

        Args:
            task_store: TaskStore for persistence.
            current_layer_ids: Task IDs in the current (interrupted) layer.
            all_tasks: All tasks in the run.
        """
        for task in all_tasks:
            if task.status not in (TaskStatus.completed, TaskStatus.failed):
                try:
                    task_store.update_status(task.id, TaskStatus.cancelled)
                except Exception:
                    logger.warning("Failed to cancel task %s", task.id, exc_info=True)
