"""LLM 실행 로깅 — 원본 응답 보존 (Phase 3A.2 §4).

개인 디버깅용 — SQLite 테이블 또는 JSONL. 여기서는 SQLite 테이블을 사용한다.
API key 등 secret은 저장하지 않는다.
"""
import json
import time
import uuid
from datetime import datetime, timezone

from ..db.models import Base, utcnow
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column


class LLMRunORM(Base):
    """LLM 호출 단위 로그 — 원본 응답과 검증 결과를 모두 보존."""
    __tablename__ = "llm_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex[:16])
    run_id: Mapped[str] = mapped_column(String, index=True)  # canary-1, golden-59 등
    review_id: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)

    raw_response: Mapped[str] = mapped_column(Text)        # LLM 원본 출력
    validated_result: Mapped[dict] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list] = mapped_column(JSON, nullable=True)

    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)  # 1=첫 성공, 2=repair 성공, 3=폴백

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def log_llm_run(session, run_id: str, review_id: str, model: str, prompt_version: str,
                input_hash: str, raw_response: str, validated_result: dict | None,
                validation_errors: list | None, latency_ms: int,
                input_tokens: int, output_tokens: int, attempts: int):
    """LLM 실행 결과를 llm_runs 테이블에 저장."""
    run = LLMRunORM(
        run_id=run_id,
        review_id=review_id,
        model=model,
        prompt_version=prompt_version,
        input_hash=input_hash,
        raw_response=raw_response,
        validated_result=validated_result,
        validation_errors=validation_errors,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        attempts=attempts,
    )
    session.add(run)
    session.commit()
    return run.id


def canary_summary(session, run_id: str) -> dict:
    """Canary 실행 결과 요약 (Phase 3A.2 §7)."""
    from sqlalchemy import select
    runs = session.execute(
        select(LLMRunORM).where(LLMRunORM.run_id == run_id)
    ).scalars().all()

    if not runs:
        return {"error": "no runs found"}

    total = len(runs)
    first_pass = sum(1 for r in runs if r.attempts == 1)
    repair_success = sum(1 for r in runs if r.attempts == 2)
    fallback = sum(1 for r in runs if r.attempts >= 3)

    latencies = sorted(r.latency_ms for r in runs)
    median = latencies[total // 2] if total else 0
    p95 = latencies[int(total * 0.95)] if total > 1 else latencies[-1] if latencies else 0

    tokens_in = sum(r.input_tokens for r in runs)
    tokens_out = sum(r.output_tokens for r in runs)

    # Evidence 검증
    total_signals = 0
    valid_quotes = 0
    hallucinated = 0
    for r in runs:
        if r.validated_result:
            ad_sigs = r.validated_result.get("ad_signals", [])
            auth_sigs = r.validated_result.get("authentic_signals", [])
            total_signals += len(ad_sigs) + len(auth_sigs)
            # 검증을 통과한 signal 수 (검증 후 저장된 것)
            valid_quotes += len(ad_sigs) + len(auth_sigs)
            dropped = r.validated_result.get("flags", {}).get("signals_dropped", 0)
            hallucinated += dropped

    return {
        "api_stability": {
            "total": total,
            "success": total - fallback,
            "first_pass_success": first_pass,
            "repair_success": repair_success,
            "fallback": fallback,
        },
        "structured_output": {
            "first_pass_rate": round(first_pass / total, 4) if total else None,
            "repair_rate": round(repair_success / total, 4) if total else None,
            "validation_failure_rate": round(fallback / total, 4) if total else None,
        },
        "evidence": {
            "total_signals": total_signals,
            "valid_quotes": valid_quotes,
            "hallucinated_quotes": hallucinated,
        },
        "performance": {
            "median_latency_ms": median,
            "p95_latency_ms": p95,
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    }
