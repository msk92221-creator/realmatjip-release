"""시스템 API — 메타 정보와 전체 백업 export."""
from fastapi import APIRouter, Request
from sqlalchemy import select

from ..db.models import (
    AppSettingORM,
    JobORM,
    ManualLabelORM,
    RestaurantORM,
    RestaurantScoreORM,
    ReviewAnalysisORM,
    ReviewORM,
)
from .reviews import AD_FILTER_LEVELS

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/meta")
def meta(request: Request):
    cfg = request.app.state.scoring_config
    with request.app.state.session_factory() as session:
        analysis = session.execute(
            select(ReviewAnalysisORM).order_by(ReviewAnalysisORM.review_id).limit(1)
        ).scalar_one_or_none()
        settings = {s.key: s.value for s in session.execute(select(AppSettingORM)).scalars()}
    return {
        "algorithm_version": cfg.algorithm_version,
        "analyzer": None if analysis is None else analysis.analyzer,
        "prompt_version": None if analysis is None else analysis.prompt_version,
        "schema_version": settings.get("schema_version"),
        "ad_filter_levels": AD_FILTER_LEVELS,
        "auth_required": bool(request.app.state.settings.auth_token),
    }


@router.get("/backup/export")
def backup_export(request: Request):
    """전체 덤프 — 앱/서버 재설치 시 복구용 (스펙: 데이터 백업은 중요 자산)."""
    with request.app.state.session_factory() as session:
        return {
            "restaurants": [
                {"id": r.id, "name": r.name, "category": r.category, "address": r.address,
                 "lat": r.lat, "lng": r.lng}
                for r in session.execute(select(RestaurantORM)).scalars()
            ],
            "reviews": [
                {"id": r.id, "restaurant_id": r.restaurant_id, "source": r.source,
                 "rating": r.rating, "text": r.text, "text_hash": r.text_hash,
                 "reviewer_review_count": r.reviewer_review_count,
                 "reviewed_at": r.reviewed_at.isoformat(),
                 "collected_at": r.collected_at.isoformat(),
                 "duplicate_of": r.duplicate_of, "raw_payload": r.raw_payload}
                for r in session.execute(select(ReviewORM)).scalars()
            ],
            "review_analysis": [
                {"review_id": a.review_id, "analyzer": a.analyzer,
                 "prompt_version": a.prompt_version,
                 "ad_probability": a.ad_probability, "ad_confidence": a.ad_confidence,
                 "authenticity": a.authenticity, "specificity": a.specificity,
                 "local_probability": a.local_probability, "sentiment": a.sentiment,
                 "visit_context": a.visit_context, "summary": a.summary,
                 "pseudo_rating": a.pseudo_rating, "flags": a.flags}
                for a in session.execute(select(ReviewAnalysisORM)).scalars()
            ],
            "manual_labels": [
                {"review_id": l.review_id, "ad_label": l.ad_label,
                 "manipulation_label": l.manipulation_label,
                 "reason": l.reason, "evidence": l.evidence, "dataset": l.dataset,
                 "labeled_at": l.labeled_at.isoformat()}
                for l in session.execute(select(ManualLabelORM)).scalars()
            ],
            "restaurant_scores": [
                {"restaurant_id": s.restaurant_id, "algorithm_version": s.algorithm_version,
                 "batch_id": s.batch_id, "calculated_at": s.calculated_at.isoformat(),
                 "overall_a": s.overall_a, "overall_b": s.overall_b,
                 "n_raw": s.n_raw, "n_eff": s.n_eff,
                 "evidence_strength": s.evidence_strength}
                for s in session.execute(select(RestaurantScoreORM)).scalars()
            ],
            "jobs": [
                {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress}
                for j in session.execute(select(JobORM)).scalars()
            ],
        }
