from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import SchedulerRun


def start_scheduler_run(
    session: Session,
    *,
    job_name: str,
    scheduled_at: datetime,
    started_at: datetime,
) -> SchedulerRun:
    run = SchedulerRun(
        job_name=job_name,
        scheduled_at=scheduled_at,
        started_at=started_at,
        status="RUNNING",
    )
    session.add(run)
    session.flush()
    return run


def finish_scheduler_run(
    session: Session,
    run: SchedulerRun,
    *,
    status: str,
    finished_at: datetime,
    error: str | None = None,
) -> SchedulerRun:
    run.status = status
    run.finished_at = finished_at
    run.error = error
    session.flush()
    return run
