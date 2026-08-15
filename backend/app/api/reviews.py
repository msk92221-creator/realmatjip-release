"""리뷰 조회 + 수동 라벨 API (2축 분리, Phase 3A.1).

광고 필터 강도(기본/엄격/매우 엄격)는 스펙 §26 값."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from typing import Literal

from ..config import MANIPULATION_LABELS, MANUAL_LABEL_VALUES
from ..db.models import ManualLabelORM, RestaurantORM, ReviewAnalysisORM, ReviewORM, utcnow

router = APIRouter(prefix="/api", tags=["reviews"])

AD_FILTER_LEVELS = {"basic": 0.7, "strict": 0.4, "very_strict": 0.2}


@router.get("/restaurants/{restaurant_id}/reviews")
def list_reviews(
    request: Request,
    restaurant_id: str,
    ad_filter: str = Query(default="basic", pattern="^(off|basic|strict|very_strict)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    threshold = AD_FILTER_LEVELS.get(ad_filter)
    with request.app.state.session_factory() as session:
        if session.get(RestaurantORM, restaurant_id) is None:
            raise HTTPException(404, "restaurant not found")
        analyses = {
            a.review_id: a
            for a in session.execute(
                select(ReviewAnalysisORM).join(ReviewORM)
                .where(ReviewORM.restaurant_id == restaurant_id)
            ).scalars()
        }
        labels = {
            l.review_id: l
            for l in session.execute(
                select(ManualLabelORM).join(ReviewORM)
                .where(ReviewORM.restaurant_id == restaurant_id)
            ).scalars()
        }
        reviews = (
            session.execute(
                select(ReviewORM).where(ReviewORM.restaurant_id == restaurant_id)
                .order_by(ReviewORM.reviewed_at.desc())
            ).scalars().all()
        )

    items = []
    for review in reviews:
        analysis = analyses.get(review.id)
        ad_probability = analysis.ad_probability if analysis else None
        if threshold is not None and ad_probability is not None and ad_probability >= threshold:
            continue
        label_row = labels.get(review.id)
        items.append({
            "id": review.id, "source": review.source, "rating": review.rating,
            "text": review.text, "reviewed_at": review.reviewed_at.isoformat(),
            "duplicate_of": review.duplicate_of,
            "analysis": None if analysis is None else {
                "analyzer": analysis.analyzer,
                "ad_probability": analysis.ad_probability,
                "ad_confidence": analysis.ad_confidence,
                "authenticity": analysis.authenticity,
                "specificity": analysis.specificity,
                "local_probability": analysis.local_probability,
                "repeat_visit": (analysis.visit_context or {}).get("repeat_visit"),
                "negative_points": (analysis.visit_context or {}).get("negative_points_present"),
                "pseudo_rating": analysis.pseudo_rating,
                "summary": analysis.summary,
            },
            "manual_ad_label": label_row.ad_label if label_row else None,
            "manual_manipulation_label": label_row.manipulation_label if label_row else None,
            "manual_reason": label_row.reason if label_row else None,
        })
        if len(items) >= limit:
            break

    return {
        "restaurant_id": restaurant_id,
        "ad_filter": ad_filter,
        "threshold": threshold,
        "total": len(reviews),
        "returned": len(items),
        "items": items,
    }


class LabelBody(BaseModel):
    """2축 라벨 — 광고(ad_label)와 조작(manipulation_label)은 독립적으로 관리한다."""
    ad_label: Literal["ad", "likely_ad", "ambiguous", "normal"] | None = None
    manipulation_label: Literal["suspicious", "ambiguous", "normal"] | None = None
    reason: str = ""
    evidence: str = ""
    dataset: Literal["natural", "challenge", ""] = ""


@router.post("/reviews/{review_id}/label")
def set_manual_label(request: Request, review_id: str, body: LabelBody):
    """수동 판단 저장/해제.

    - ad_label → effective_ad_probability에만 반영 (재계산 시)
    - manipulation_label → manipulation evaluation/calibration에만 사용
    - 둘 다 null이면 라벨 삭제
    """
    if body.ad_label is None and body.manipulation_label is None and not body.reason:
        with request.app.state.session_factory() as session:
            if session.get(ReviewORM, review_id) is None:
                raise HTTPException(404, "review not found")
            existing = session.get(ManualLabelORM, review_id)
            if existing is not None:
                session.delete(existing)
                session.commit()
            return {"review_id": review_id, "cleared": True}

    with request.app.state.session_factory() as session:
        if session.get(ReviewORM, review_id) is None:
            raise HTTPException(404, "review not found")
        existing = session.get(ManualLabelORM, review_id)
        if existing is None:
            session.add(ManualLabelORM(
                review_id=review_id,
                ad_label=body.ad_label,
                manipulation_label=body.manipulation_label,
                reason=body.reason,
                evidence=body.evidence,
                dataset=body.dataset,
            ))
        else:
            if body.ad_label is not None:
                existing.ad_label = body.ad_label
            if body.manipulation_label is not None:
                existing.manipulation_label = body.manipulation_label
            existing.reason = body.reason or existing.reason
            existing.evidence = body.evidence or existing.evidence
            existing.dataset = body.dataset or existing.dataset
            existing.labeled_at = utcnow()
        session.commit()

    return {
        "review_id": review_id,
        "ad_label": body.ad_label,
        "manipulation_label": body.manipulation_label,
        "valid_ad_labels": sorted(MANUAL_LABEL_VALUES),
        "valid_manipulation_labels": list(MANIPULATION_LABELS),
    }
