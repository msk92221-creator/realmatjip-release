"""미분석 리뷰 분석 잡 (스펙 §7) — 캐시 우선, 비용 가드, 부분 실패 허용.

    Review(분석 없음)
      → analysis_cache(text_hash+model+prompt_version+analysis_version) 조회
          hit  → 캐시 복원 (무비용)
          miss → analyzer.analyze → 검증 → review_analysis + cache 저장
      → 전송 오류는 failed로 기록하고 계속 (job 중단 금지)
      → 설정/모델 오류는 job 즉시 실패 (AnalyzerConfigError)
"""
from sqlalchemy import select

from ..analysis import ReviewAnalysis
from ..analysis.analyzer import AnalyzerConfigError, AnalyzerTransportError
from ..analysis.schema import (
    analysis_from_cache_dict,
    analysis_to_cache_dict,
    load_system_prompt,
)
from ..analysis.input_hash import llm_input_hash
from ..db.mappers import analysis_to_row
from ..db.models import AnalysisCacheORM, JobORM, ReviewAnalysisORM, ReviewORM
from ..models import Review

from .limits import AnalyzeLimits, estimate_cost

BASE_MESSAGE_CHARS = len(load_system_prompt()) + 4000  # system + few-shot 근사
ESTIMATED_OUTPUT_TOKENS = 350


def _pending_reviews(session) -> list[Review]:
    analyzed = select(ReviewAnalysisORM.review_id)
    return [
        Review(
            id=row.id, restaurant_id=row.restaurant_id, source=row.source,
            rating=row.rating, text=row.text, reviewed_at=row.reviewed_at,
            reviewer_review_count=row.reviewer_review_count,
        )
        for row in session.execute(
            select(ReviewORM).where(ReviewORM.id.not_in(analyzed))
            .order_by(ReviewORM.reviewed_at.asc())
        ).scalars()
    ]


def _cache_key_hashes(session, analyzer_name: str, prompt_version: str) -> set[str]:
    return set(
        session.execute(
            select(AnalysisCacheORM.text_hash).where(
                AnalysisCacheORM.analyzer == analyzer_name,
                AnalysisCacheORM.prompt_version == prompt_version,
            )
        ).scalars()
    )


def estimate_analysis(session, analyzer_name: str, prompt_version: str,
                      limits: AnalyzeLimits) -> dict:
    """dry-run — 실제 호출 전 예상 사용량 (스펙 §6)."""
    pending = _pending_reviews(session)
    cached_hashes = _cache_key_hashes(session, analyzer_name, prompt_version)
    to_call = [r for r in pending if llm_input_hash(r) not in cached_hashes]
    cached = len(pending) - len(to_call)

    tokens_input = sum(BASE_MESSAGE_CHARS // 3 + len(r.text) // 3 + 60 for r in to_call)
    tokens_output = ESTIMATED_OUTPUT_TOKENS * len(to_call)
    cost = estimate_cost(limits, tokens_input, tokens_output)
    return {
        "analyzer": analyzer_name,
        "prompt_version": prompt_version,
        "pending_total": len(pending),
        "to_analyze": len(to_call),
        "cached_hits": cached,
        "estimated_tokens_input": tokens_input,
        "estimated_tokens_output": tokens_output,
        "estimated_cost": cost,
        "limits": {
            "max_reviews_per_job": limits.max_reviews_per_job,
            "max_estimated_tokens_per_job": limits.max_estimated_tokens_per_job,
            "max_estimated_cost_per_job": limits.max_estimated_cost_per_job,
        },
        # 비용/토큰 상한은 job 시작 자체를 막는 게이트. 리뷰 수 상한은 잘라내기 대상.
        "within_limits": (
            tokens_input + tokens_output <= limits.max_estimated_tokens_per_job
            and cost <= limits.max_estimated_cost_per_job
        ),
        "reviews_exceed_cap": len(to_call) > limits.max_reviews_per_job,
    }


def _set_progress(session_factory, job_id: int, **fields) -> None:
    error = fields.pop("error", None)
    status = fields.pop("status", None)
    with session_factory() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if error is not None:
            job.error = error
        progress = dict(job.progress or {})
        progress.update(fields)
        job.progress = progress
        session.commit()


def execute_analyze_job(session_factory, job_id: int, analyzer, limits: AnalyzeLimits) -> None:
    analyzer_name = analyzer.name
    _set_progress(session_factory, job_id, status="running", analyzer=analyzer_name)

    try:
        if hasattr(analyzer, "validate_model"):
            analyzer.validate_model()
    except AnalyzerConfigError as exc:
        _set_progress(session_factory, job_id, status="failed", error=str(exc))
        raise
    except AnalyzerTransportError as exc:
        _set_progress(session_factory, job_id, status="failed",
                      error=f"모델 확인 실패: {exc}")
        raise

    with session_factory() as session:
        estimate = estimate_analysis(session, analyzer_name,
                                     _prompt_version_of(analyzer), limits)
    to_call = estimate["to_analyze"]
    if not estimate["within_limits"]:
        message = (
            f"예상 사용량이 상한 초과 — 대상 {to_call}개 리뷰, "
            f"토큰 {estimate['estimated_tokens_input'] + estimate['estimated_tokens_output']:,}, "
            f"비용 ${estimate['estimated_cost']}. "
            "MAX_*_PER_JOB 환경변수를 조정하거나 리뷰 범위를 좁히세요."
        )
        _set_progress(session_factory, job_id, status="failed", error=message)
        return
    with session_factory() as session:
        pending = _pending_reviews(session)
        cached_hashes = _cache_key_hashes(session, analyzer_name, _prompt_version_of(analyzer))
        call_targets = [r for r in pending if llm_input_hash(r) not in cached_hashes]
        truncated = len(call_targets) > limits.max_reviews_per_job
        if truncated:
            call_targets = call_targets[: limits.max_reviews_per_job]
        # 캐시 복원 대상은 무비용이므로 상한과 무관하게 항상 처리
        restore_targets = [r for r in pending if llm_input_hash(r) in cached_hashes]
        targets = restore_targets + call_targets

    progress = {
        "pending_total": len(targets), "completed": 0, "cached": 0, "failed": 0,
        "failed_ids": [], "truncated": truncated,
        "prompt_version": _prompt_version_of(analyzer),
    }
    _set_progress(session_factory, job_id, **progress)

    for review in targets:
        digest = llm_input_hash(review)
        try:
            if digest in cached_hashes:
                with session_factory() as session:
                    cache_row = session.execute(
                        select(AnalysisCacheORM).where(
                            AnalysisCacheORM.text_hash == digest,
                            AnalysisCacheORM.analyzer == analyzer_name,
                        )
                    ).scalar_one()
                    analysis = analysis_from_cache_dict(cache_row.result)
                    _upsert_analysis(session, review.id, analysis)
                progress["cached"] += 1
            else:
                analysis = analyzer.analyze(review)
                with session_factory() as session:
                    _upsert_analysis(session, review.id, analysis)
                    session.merge(AnalysisCacheORM(
                        text_hash=digest,
                        analyzer=analysis.analyzer,
                        prompt_version=analysis.prompt_version,
                        analysis_version="1",
                        result=analysis_to_cache_dict(analysis),
                    ))
                    session.commit()
                progress["completed"] += 1
                cached_hashes.add(digest)
        except AnalyzerTransportError as exc:
            progress["failed"] += 1
            progress["failed_ids"] = (progress["failed_ids"] + [review.id])[:50]
            progress["last_error"] = str(exc)[:200]
        except AnalyzerConfigError as exc:
            _set_progress(session_factory, job_id, status="failed", error=str(exc), **progress)
            raise

        tokens_in = getattr(analyzer, "tokens_input", 0)
        tokens_out = getattr(analyzer, "tokens_output", 0)
        progress.update({
            "tokens_input": tokens_in, "tokens_output": tokens_out,
            "estimated_cost": estimate_cost(limits, tokens_in, tokens_out),
        })
        _set_progress(session_factory, job_id, **progress)

    _set_progress(session_factory, job_id,
                  status="done", model=getattr(analyzer, "model", None),
                  llm_calls=getattr(analyzer, "calls", None))


def _upsert_analysis(session, review_id: str, analysis: ReviewAnalysis) -> None:
    session.merge(analysis_to_row(review_id, analysis))
    session.commit()


def _prompt_version_of(analyzer) -> str:
    return getattr(analyzer, "prompt_version", None) or "review-analysis-v1"
