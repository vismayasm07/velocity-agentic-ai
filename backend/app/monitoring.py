import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import ActionExecutionError, create_follow_up_task
from app.analysis import AnalysisWorkflowError, analyze_incident
from app.database import async_session_factory
from app.detection import DetectionScanResult, run_detection_scan
from app.models import AgentAuditEvent, BottleneckIncident, MonitoringRun, MonitoringSettings
from app.outcomes import reopen_recurred_incidents, verify_due_outcomes

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
ScanFunction = Callable[[AsyncSession], Awaitable[DetectionScanResult]]
_loop_cycle_locks: WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Lock
] = WeakKeyDictionary()


def get_loop_cycle_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _loop_cycle_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _loop_cycle_locks[loop] = lock
    return lock


class ProactiveMonitoringService:
    def __init__(
        self,
        *,
        enabled: bool,
        interval_seconds: int,
        session_factory: SessionFactory = async_session_factory,
        scan: ScanFunction = run_detection_scan,
    ) -> None:
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self._session_factory = session_factory
        self._scan = scan
        self._cycle_lock: asyncio.Lock | None = None
        self._stop_event: asyncio.Event | None = None
        self._settings_changed: asyncio.Event | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._next_scan_at: datetime | None = None

    @property
    def active(self) -> bool:
        return (
            self.enabled
            and self._scheduler_task is not None
            and not self._scheduler_task.done()
        )

    @property
    def cycle_running(self) -> bool:
        return self._cycle_lock is not None and self._cycle_lock.locked()

    @property
    def next_scan_at(self) -> datetime | None:
        return self._next_scan_at

    async def start(self) -> None:
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._cycle_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._settings_changed = asyncio.Event()
        self._scheduler_task = asyncio.create_task(
            self._schedule(), name="proactive-bottleneck-monitor"
        )

    async def stop(self) -> None:
        task = self._scheduler_task
        if task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        if self._settings_changed is not None:
            self._settings_changed.set()
        await task
        self._scheduler_task = None
        self._cycle_lock = None
        self._stop_event = None
        self._settings_changed = None
        self._next_scan_at = None

    async def run_once(self) -> MonitoringRun | None:
        if self._cycle_lock is None:
            self._cycle_lock = asyncio.Lock()
        if self._cycle_lock.locked():
            return None
        async with self._cycle_lock:
            async with get_loop_cycle_lock():
                async with self._session_factory() as session:
                    active_settings = await session.scalar(
                        select(MonitoringSettings).limit(1)
                    )
                if active_settings is not None:
                    self.enabled = active_settings.monitoring_enabled
                    self.interval_seconds = active_settings.scan_interval_seconds
                if not self.enabled:
                    return None
                started_at = datetime.now(UTC)
                async with self._session_factory() as session:
                    run = MonitoringRun(
                        started_at=started_at,
                        deals_scanned=0,
                        incidents_created=0,
                        incidents_updated=0,
                        errors_encountered=0,
                        status="RUNNING",
                    )
                    session.add(run)
                    await session.commit()
                    await session.refresh(run)
                    run_id = run.id

                result: DetectionScanResult | None = None
                cycle_error: Exception | None = None
                try:
                    async with self._session_factory() as session:
                        result = await self._scan(session)
                except Exception as error:
                    cycle_error = error

                async with self._session_factory() as session:
                    run = await session.get(MonitoringRun, run_id)
                    if run is None:
                        raise RuntimeError(f"Monitoring run {run_id} was not found")
                    run.completed_at = datetime.now(UTC)
                    if result is not None:
                        run.deals_scanned = result.deals_scanned
                        run.incidents_created = result.incidents_created
                        run.incidents_updated = result.incidents_updated
                        run.errors_encountered = len(result.errors)
                        run.status = "COMPLETED_WITH_ERRORS" if result.errors else "COMPLETED"
                        details: dict[str, object] = {
                            "deals_scanned": result.deals_scanned,
                            "incidents_created": result.incidents_created,
                            "incidents_updated": result.incidents_updated,
                            "errors": result.errors,
                        }
                    else:
                        run.errors_encountered = 1
                        run.status = "FAILED"
                        details = {"error": str(cycle_error)}
                    session.add(
                        AgentAuditEvent(
                            monitoring_run_id=run.id,
                            event_type="MONITORING_CYCLE",
                            status=run.status,
                            details=details,
                        )
                    )
                    await session.commit()
                    await session.refresh(run)
                if result is not None and active_settings is not None:
                    await self._run_automatic_rca(result, active_settings, run.id)
                    try:
                        async with self._session_factory() as session:
                            await verify_due_outcomes(session, monitoring_run_id=run.id)
                            await reopen_recurred_incidents(session)
                    except Exception as error:
                        async with self._session_factory() as session:
                            persisted_run = await session.get(MonitoringRun, run.id)
                            if persisted_run is not None:
                                persisted_run.errors_encountered += 1
                                persisted_run.status = "COMPLETED_WITH_ERRORS"
                            session.add(
                                AgentAuditEvent(
                                    monitoring_run_id=run.id,
                                    event_type="OUTCOME_VERIFICATION_FAILED",
                                    status="FAILED",
                                    details={"error": str(error)},
                                )
                            )
                            await session.commit()
                return run

    async def _run_automatic_rca(
        self,
        result: DetectionScanResult,
        settings: MonitoringSettings,
        monitoring_run_id: UUID,
    ) -> None:
        if not settings.automatic_rca_enabled or not result.analysis_candidate_ids:
            return
        async with self._session_factory() as session:
            incidents = list(
                await session.scalars(
                    select(BottleneckIncident).where(
                        BottleneckIncident.id.in_(result.analysis_candidate_ids),
                        BottleneckIncident.status == "open",
                    )
                )
            )
            eligible_ids = []
            for incident in incidents:
                if incident.risk_score >= settings.automatic_rca_min_risk_score:
                    eligible_ids.append(incident.id)
                    continue
                session.add(
                    AgentAuditEvent(
                        incident_id=incident.id,
                        monitoring_run_id=monitoring_run_id,
                        event_type="AUTOMATIC_ANALYSIS_SKIPPED",
                        status="SKIPPED",
                        details={
                            "reason": "BELOW_RISK_THRESHOLD",
                            "risk_score": incident.risk_score,
                            "minimum_risk_score": settings.automatic_rca_min_risk_score,
                        },
                    )
                )
            await session.commit()

        semaphore = asyncio.Semaphore(3)

        async def run_analysis(incident_id: UUID) -> None:
            async with semaphore:
                try:
                    async with self._session_factory() as session:
                        analysis = await analyze_incident(
                            session,
                            incident_id,
                            trigger="AUTOMATIC",
                            monitoring_run_id=monitoring_run_id,
                        )
                except AnalysisWorkflowError:
                    return
                if (
                    analysis is None
                    or not settings.automatic_safe_actions_enabled
                    or analysis.status != "COMPLETED"
                    or analysis.action_type != "CREATE_FOLLOW_UP"
                    or analysis.approval_required is not False
                    or analysis.confidence is None
                    or float(analysis.confidence) * 100
                    < settings.automatic_rca_min_risk_score
                ):
                    return
                try:
                    async with self._session_factory() as session:
                        await create_follow_up_task(
                            session,
                            incident_id,
                            None,
                            execution_source="AUTOMATIC",
                            due_hours=settings.follow_up_due_hours,
                            monitoring_run_id=monitoring_run_id,
                        )
                except Exception as error:
                    async with self._session_factory() as session:
                        session.add(
                            AgentAuditEvent(
                                incident_id=incident_id,
                                analysis_id=analysis.id,
                                monitoring_run_id=monitoring_run_id,
                                event_type="AUTOMATIC_ACTION_FAILED",
                                status="FAILED",
                                details={
                                    "action_type": "CREATE_FOLLOW_UP",
                                    "error": (
                                        error.message
                                        if isinstance(error, ActionExecutionError)
                                        else str(error)
                                    ),
                                },
                            )
                        )
                        await session.commit()

        await asyncio.gather(*(run_analysis(incident_id) for incident_id in eligible_ids))

    async def latest_run(self, session: AsyncSession) -> MonitoringRun | None:
        return await session.scalar(
            select(MonitoringRun).order_by(MonitoringRun.started_at.desc()).limit(1)
        )

    def apply_settings(self, settings: MonitoringSettings) -> None:
        self.enabled = settings.monitoring_enabled
        self.interval_seconds = settings.scan_interval_seconds
        if self._settings_changed is not None:
            self._settings_changed.set()

    async def _schedule(self) -> None:
        if self._stop_event is None or self._settings_changed is None:
            raise RuntimeError("Monitoring service has not been started")
        stop_event = self._stop_event
        settings_changed = self._settings_changed
        try:
            while not stop_event.is_set():
                await self.run_once()
                if not self.enabled:
                    self._next_scan_at = None
                else:
                    self._next_scan_at = datetime.now(UTC) + timedelta(
                        seconds=self.interval_seconds
                    )
                try:
                    await asyncio.wait_for(
                        settings_changed.wait(), timeout=self.interval_seconds
                    )
                    settings_changed.clear()
                except TimeoutError:
                    continue
        finally:
            self._next_scan_at = None


async def iter_monitoring_runs(
    session: AsyncSession, limit: int = 25
) -> AsyncIterator[MonitoringRun]:
    runs = await session.stream_scalars(
        select(MonitoringRun).order_by(MonitoringRun.started_at.desc()).limit(limit)
    )
    async for run in runs:
        yield run