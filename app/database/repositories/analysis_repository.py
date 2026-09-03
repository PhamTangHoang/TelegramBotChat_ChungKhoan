from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.audit.snapshot import build_input_hash
from app.database.models import AnalysisRun


def create_analysis_run(
    session: Session,
    *,
    symbol: str,
    exchange: str,
    trading_date: date,
    as_of: datetime,
    data_snapshot: dict[str, Any],
    indicator_snapshot: dict[str, Any],
    rule_result: dict[str, Any],
    data_provenance: dict[str, Any],
    prompt_version: str,
    rule_version: str,
    data_schema_version: str,
    analysis_kind: str,
    is_final: bool,
    model: str | None = None,
    llm_response: dict[str, Any] | None = None,
    explanation_conflict: bool = False,
) -> AnalysisRun:
    input_hash = build_input_hash(
        data_snapshot=data_snapshot,
        indicator_snapshot=indicator_snapshot,
        rule_result=rule_result,
        rule_version=rule_version,
        data_schema_version=data_schema_version,
    )
    run = AnalysisRun(
        symbol=symbol,
        exchange=exchange,
        trading_date=trading_date,
        as_of=as_of,
        data_snapshot=data_snapshot,
        indicator_snapshot=indicator_snapshot,
        rule_result=rule_result,
        data_provenance=data_provenance,
        prompt_version=prompt_version,
        rule_version=rule_version,
        data_schema_version=data_schema_version,
        model=model,
        llm_response=llm_response,
        rule_signal=str(rule_result["signal"]),
        explanation_conflict=explanation_conflict,
        input_hash=input_hash,
        analysis_kind=analysis_kind,
        is_final=is_final,
    )
    session.add(run)
    session.flush()
    return run


def attach_llm_response(
    session: Session,
    run: AnalysisRun,
    *,
    model: str,
    llm_response: dict[str, Any],
    explanation_conflict: bool,
) -> AnalysisRun:
    run.model = model
    run.llm_response = llm_response
    run.explanation_conflict = explanation_conflict
    session.flush()
    return run
