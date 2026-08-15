"""관리 API — 재계산/분석 잡, Import preview/commit, 통계, calibration.
실데이터 자동 수집(Places/네이버/카카오)은 Phase 3B."""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text

from ..analysis.analyzer import AnalyzerConfigError, create_analyzer_from_env
from ..db.models import (
    JobORM,
    ManualLabelORM,
    RestaurantORM,
    RestaurantScoreORM,
    ReviewAnalysisORM,
    ReviewORM,
)
from ..db.seed import seed
from ..importer.service import commit_import, preview_import
from ..jobs.runner import create_job, execute_recalculate
from ..pipeline.analyze import estimate_analysis, execute_analyze_job
from ..pipeline.calibration import calibration_report
from ..pipeline.limits import limits_from_env

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/seed")
def seed_endpoint(request: Request, reset: bool = False):
    with request.app.state.session_factory() as session:
        result = seed(session, reset=reset)
    return {"seeded": result, "reset": reset}


@router.post("/recalculate")
def recalculate(request: Request, background: BackgroundTasks):
    """전체 점수 재계산(비동기 잡). LLM 호출 없음 — 저장된 분석만 재집계."""
    cfg = request.app.state.scoring_config
    job_id = create_job(request.app.state.session_factory, kind="recalculate")
    background.add_task(
        execute_recalculate, request.app.state.session_factory, job_id, cfg
    )
    return {"job_id": job_id, "kind": "recalculate", "algorithm_version": cfg.algorithm_version}


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: int):
    with request.app.state.session_factory() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return {
            "id": job.id, "kind": job.kind, "status": job.status,
            "progress": job.progress, "error": job.error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }


# ── 수동 Import (스펙 §1~§2) ──────────────────────────────────


class ImportBody(BaseModel):
    format: str  # json | csv
    content: str


@router.post("/import/preview")
def import_preview(request: Request, body: ImportBody):
    """Dry run — DB 변경 없이 신규/중복/오류와 예상 삽입 수를 보여준다."""
    if body.format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    with request.app.state.session_factory() as session:
        preview = preview_import(session, body.format, body.content)
    return {
        "total": preview.total,
        "valid": preview.valid,
        "invalid": preview.invalid,
        "exact_duplicates": preview.exact_duplicates,
        "estimated_new_reviews": preview.estimated_new_reviews,
        "new_restaurants": preview.new_restaurants,
        "matched_restaurants": preview.matched_restaurants,
        "errors": [{"row": e.row, "field": e.field, "reason": e.reason} for e in preview.errors],
        "restaurants": preview.restaurants,
    }


@router.post("/import/commit")
def import_commit(request: Request, body: ImportBody):
    """사용자가 preview를 확인한 뒤 실제 반영. 원본 행은 raw_payload에 보존된다."""
    if body.format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    with request.app.state.session_factory() as session:
        result = commit_import(session, body.format, body.content)
    return {
        "inserted_restaurants": result.inserted_restaurants,
        "inserted_reviews": result.inserted_reviews,
        "skipped_duplicates": result.skipped_duplicates,
        "invalid": result.invalid,
        "errors": [{"row": e.row, "field": e.field, "reason": e.reason} for e in result.errors],
    }


# ── LLM 분석 (스펙 §3~§7) ────────────────────────────────────


@router.post("/analyze/preview")
def analyze_preview(request: Request):
    """dry-run — 분석 대상, 캐시 hit, 예상 토큰/비용과 상한 이내 여부."""
    analyzer = create_analyzer_from_env()
    limits = limits_from_env()
    with request.app.state.session_factory() as session:
        return estimate_analysis(session, analyzer.name, analyzer.prompt_version, limits)


@router.post("/analyze-pending")
def analyze_pending(request: Request, background: BackgroundTasks):
    """미분석 리뷰 LLM 분석 잡. 캐시 우선, 비용 상한 검사 후 실행."""
    try:
        analyzer = create_analyzer_from_env()
    except AnalyzerConfigError as exc:
        raise HTTPException(400, str(exc))
    limits = limits_from_env()
    job_id = create_job(request.app.state.session_factory, kind="analyze-pending")
    background.add_task(
        execute_analyze_job, request.app.state.session_factory, job_id, analyzer, limits
    )
    return {
        "job_id": job_id, "kind": "analyze-pending",
        "analyzer": analyzer.name, "prompt_version": analyzer.prompt_version,
    }


@router.get("/calibration")
def calibration(request: Request, threshold: float = 0.7):
    """2축 분리 + Natural/Challenge Set 구분 calibration 보고 (Phase 3A.1)."""
    with request.app.state.session_factory() as session:
        return calibration_report(session, ad_threshold=threshold)


@router.get("/stats")
def stats(request: Request):
    cfg = request.app.state.scoring_config
    with request.app.state.session_factory() as session:
        restaurants = session.scalar(select(func.count(RestaurantORM.id)))
        reviews = session.scalar(select(func.count(ReviewORM.id)))
        analyzed = session.scalar(select(func.count(ReviewAnalysisORM.review_id)))
        ad_labels = dict(
            session.execute(
                select(ManualLabelORM.ad_label, func.count(ManualLabelORM.review_id))
                .where(ManualLabelORM.ad_label.is_not(None))
                .group_by(ManualLabelORM.ad_label)
            ).all()
        )
        manipulation_labels = dict(
            session.execute(
                select(ManualLabelORM.manipulation_label, func.count(ManualLabelORM.review_id))
                .where(ManualLabelORM.manipulation_label.is_not(None))
                .group_by(ManualLabelORM.manipulation_label)
            ).all()
        )
        by_source = dict(
            session.execute(
                select(ReviewORM.source, func.count(ReviewORM.id)).group_by(ReviewORM.source)
            ).all()
        )
        latest = session.execute(
            select(RestaurantScoreORM)
            .where(RestaurantScoreORM.algorithm_version == cfg.algorithm_version)
            .order_by(RestaurantScoreORM.id.desc()).limit(1)
        ).scalar_one_or_none()
        dup_flagged = session.scalar(
            select(func.count(ReviewORM.id)).where(ReviewORM.duplicate_of.is_not(None))
        )
    return {
        "restaurants": restaurants,
        "reviews": reviews,
        "analyzed": analyzed,
        "unanalyzed": (reviews or 0) - (analyzed or 0),
        "duplicate_flagged": dup_flagged,
        "ad_labels": ad_labels,
        "manipulation_labels": manipulation_labels,
        "reviews_by_source": by_source,
        "latest_score": None if latest is None else {
            "algorithm_version": latest.algorithm_version,
            "batch_id": latest.batch_id,
            "calculated_at": latest.calculated_at.isoformat(),
        },
    }
