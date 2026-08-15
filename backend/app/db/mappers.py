"""ORM ↔ 도메인(순수 scoring 모델) 변환. scoring 엔진은 DB를 모른다 —
이 매퍼가 유일한 접점이다 (API/DB가 scoring 내부로 침투하지 않는 구조)."""
import hashlib

from ..analysis import ReviewAnalysis, Signal
from ..models import Restaurant, Review
from ..scoring.engine import RestaurantResult
from .models import (
    RestaurantORM,
    RestaurantScoreORM,
    ReviewAnalysisORM,
    ReviewORM,
    utcnow,
)
from ..scoring.duplicates import normalize_text


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


# ── 도메인 → ORM ──────────────────────────────────────────────

def restaurant_to_row(rest: Restaurant) -> RestaurantORM:
    return RestaurantORM(
        id=rest.id, name=rest.name, category=rest.category,
        address=rest.address, lat=rest.lat, lng=rest.lng,
    )


def review_to_row(review: Review) -> ReviewORM:
    return ReviewORM(
        id=review.id, restaurant_id=review.restaurant_id, source=review.source,
        reviewer_review_count=review.reviewer_review_count,
        rating=review.rating, text=review.text, text_hash=text_hash(review.text),
        raw_payload={"origin": "fixture", "text": review.text, "rating": review.rating},
        reviewed_at=review.reviewed_at,
    )


def analysis_to_row(review_id: str, an: ReviewAnalysis) -> ReviewAnalysisORM:
    return ReviewAnalysisORM(
        review_id=review_id, analyzer=an.analyzer, prompt_version=an.prompt_version,
        ad_probability=an.ad_probability, ad_confidence=an.ad_confidence,
        authenticity=an.authenticity, specificity=an.specificity,
        local_probability=an.local_probability,
        sentiment=an.sentiment, visit_context=an.visit_context,
        ad_signals=[{"code": s.code, "quote": s.quote} for s in an.ad_signals],
        authentic_signals=[{"code": s.code, "quote": s.quote} for s in an.authentic_signals],
        summary=an.summary, pseudo_rating=an.pseudo_rating, flags=an.flags,
        analyzed_at=utcnow(),
    )


def score_to_row(res: RestaurantResult, batch_id: str, algorithm_version: str) -> RestaurantScoreORM:
    sub = res.sub
    return RestaurantScoreORM(
        restaurant_id=res.restaurant.id, batch_id=batch_id,
        algorithm_version=algorithm_version,
        overall_a=res.overall_a.score, overall_b=res.overall_b.score,
        rating_adjusted=sub.rating_adjusted, local=sub.local, trust=sub.trust,
        ad_free=sub.ad_free, food=sub.food, value=sub.value, repeat=sub.repeat,
        consistency=res.consistency, longevity=res.longevity,
        manipulation_score=res.manipulation.score,
        n_raw=sub.n_raw, n_eff=sub.n_eff, local_evidence=sub.local_evidence,
        evidence_strength=sub.evidence_strength, local_badge=res.local_badge,
        dup_count=res.dup_count,
        terms_a=[[name, value, round(points, 2)] for name, value, points in res.overall_a.terms],
        terms_b=[[name, value, round(points, 2)] for name, value, points in res.overall_b.terms],
        platforms=[
            {"source": p.source, "n_reviews": p.n_reviews,
             "sum_w": round(p.sum_w, 3), "shrunk_rating": round(p.shrunk_rating, 4)}
            for p in res.platforms
        ],
    )


# ── ORM → 도메인 ──────────────────────────────────────────────

def analysis_to_domain(row: ReviewAnalysisORM) -> ReviewAnalysis:
    return ReviewAnalysis(
        analyzer=row.analyzer, prompt_version=row.prompt_version,
        ad_probability=row.ad_probability, ad_confidence=row.ad_confidence,
        authenticity=row.authenticity, specificity=row.specificity,
        local_probability=row.local_probability,
        sentiment=row.sentiment or {}, visit_context=row.visit_context or {},
        ad_signals=[Signal(code=s["code"], quote=s["quote"]) for s in (row.ad_signals or [])],
        authentic_signals=[Signal(code=s["code"], quote=s["quote"]) for s in (row.authentic_signals or [])],
        summary=row.summary or "", pseudo_rating=row.pseudo_rating,
        flags=row.flags or {},
    )


def review_to_domain(
    row: ReviewORM,
    analysis_row: ReviewAnalysisORM | None,
    manual_label: str | None,
) -> Review:
    review = Review(
        id=row.id, restaurant_id=row.restaurant_id, source=row.source,
        rating=row.rating, text=row.text, reviewed_at=row.reviewed_at,
        reviewer_review_count=row.reviewer_review_count,
        manual_label=manual_label,
    )
    if analysis_row is not None:
        review.analysis = analysis_to_domain(analysis_row)
    return review
