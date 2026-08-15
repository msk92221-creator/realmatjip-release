"""식당 목록/상세 API. 개인 규모(수백~수천 식당)이므로 정렬·필터는 앱 계층에서
수행한다 — 실데이터 규모가 커지면 SQL로 내린다."""
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from ..db.models import RestaurantORM, RestaurantScoreORM

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])

TERM_LABELS = {
    "rating": "가중 보정 평점",
    "consistency": "플랫폼 일관성",
    "repeat": "재방문 신호",
    "local": "로컬 성격",
    "longevity": "장기 안정",
    "trust": "리뷰 신뢰도",
    "manipulation": "조작 의심 감점",
}


def latest_score_rows(session, version: str) -> dict[str, RestaurantScoreORM]:
    """해당 알고리즘 버전의 최신 배치 점수만 조회 (이력은 DB에 그대로 보존)."""
    latest = (
        session.execute(
            select(RestaurantScoreORM)
            .where(RestaurantScoreORM.algorithm_version == version)
            .order_by(RestaurantScoreORM.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    )
    if latest is None:
        return {}
    rows = session.execute(
        select(RestaurantScoreORM).where(RestaurantScoreORM.batch_id == latest.batch_id)
    ).scalars()
    return {row.restaurant_id: row for row in rows}


def _summary(restaurant: RestaurantORM, score: RestaurantScoreORM, cfg) -> dict:
    return {
        "id": restaurant.id, "name": restaurant.name, "category": restaurant.category,
        "lat": restaurant.lat, "lng": restaurant.lng,
        "overall_a": score.overall_a, "overall_b": score.overall_b,
        "n_raw": score.n_raw, "n_eff": round(score.n_eff, 1),
        "evidence_strength": round(score.evidence_strength, 3),
        "evidence_label": cfg.evidence_label(score.evidence_strength),
        "local_badge": score.local_badge,
        "manipulation_score": round(score.manipulation_score, 3),
    }


@router.get("")
def list_restaurants(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    local_only: bool = False,
    min_overall: float | None = None,
    sort: str = Query(default="overall_a", pattern="^(overall_a|overall_b|name)$"),
    bbox: str | None = Query(default=None, description="lat1,lng1,lat2,lng2"),
    limit: int = Query(default=50, ge=1, le=200),
):
    cfg = request.app.state.scoring_config
    with request.app.state.session_factory() as session:
        scores = latest_score_rows(session, cfg.algorithm_version)
        restaurants = session.execute(select(RestaurantORM)).scalars().all()

    items = []
    for restaurant in restaurants:
        score = scores.get(restaurant.id)
        if score is None:
            continue  # 아직 스코어링되지 않은 식당은 목록에서 제외(데이터 없음 상태)
        if q and q not in restaurant.name and q not in restaurant.category:
            continue
        if category and category not in restaurant.category:
            continue
        if local_only and not score.local_badge:
            continue
        if min_overall is not None and (score.overall_a or 0) < min_overall:
            continue
        if bbox:
            try:
                lat1, lng1, lat2, lng2 = (float(x) for x in bbox.split(","))
            except ValueError:
                raise HTTPException(400, "bbox must be 'lat1,lng1,lat2,lng2'")
            if not (min(lat1, lat2) <= restaurant.lat <= max(lat1, lat2)
                    and min(lng1, lng2) <= restaurant.lng <= max(lng1, lng2)):
                continue
        items.append((restaurant, score))

    if sort == "name":
        items.sort(key=lambda pair: pair[0].name)
    else:
        items.sort(key=lambda pair: (getattr(pair[1], sort) or -1), reverse=True)

    return {
        "algorithm_version": cfg.algorithm_version,
        "count": len(items),
        "items": [_summary(r, s, cfg) for r, s in items[:limit]],
    }


@router.get("/{restaurant_id}")
def restaurant_detail(request: Request, restaurant_id: str):
    cfg = request.app.state.scoring_config
    with request.app.state.session_factory() as session:
        restaurant = session.get(RestaurantORM, restaurant_id)
        if restaurant is None:
            raise HTTPException(404, "restaurant not found")
        score = latest_score_rows(session, cfg.algorithm_version).get(restaurant_id)

    if score is None:
        return {
            "id": restaurant.id, "name": restaurant.name, "category": restaurant.category,
            "lat": restaurant.lat, "lng": restaurant.lng, "address": restaurant.address,
            "scores": None, "detail": None,
            "message": "점수 없음 — 재계산을 실행하세요",
        }

    explanation = [
        {"term": term, "label": TERM_LABELS.get(term, term),
         "value": round(value, 4), "points": points}
        for term, value, points in score.terms_a
    ]
    detail = {
        "subscores": {
            "rating_adjusted": round(score.rating_adjusted, 4),
            "local": round(score.local, 4), "trust": round(score.trust, 4),
            "ad_free": round(score.ad_free, 4), "food": score.food, "value": score.value,
            "repeat": round(score.repeat, 4),
        },
        "signals": {
            "consistency": round(score.consistency, 4),
            "longevity": round(score.longevity, 4),
            "manipulation_score": round(score.manipulation_score, 4),
            "dup_count": score.dup_count,
            "n_raw": score.n_raw, "n_eff": round(score.n_eff, 2),
            "local_evidence": round(score.local_evidence, 2),
            "evidence_strength": round(score.evidence_strength, 3),
            "evidence_label": cfg.evidence_label(score.evidence_strength),
            "local_badge": score.local_badge,
        },
        "explanation": explanation,   # "왜 이 점수인가" 렌더링용 (스펙 §20)
        "terms_b": score.terms_b,
        "platforms": score.platforms,
        "calculated_at": score.calculated_at.isoformat(),
    }
    return {
        "id": restaurant.id, "name": restaurant.name, "category": restaurant.category,
        "lat": restaurant.lat, "lng": restaurant.lng, "address": restaurant.address,
        "scores": {"overall_a": score.overall_a, "overall_b": score.overall_b},
        "detail": detail,
    }
