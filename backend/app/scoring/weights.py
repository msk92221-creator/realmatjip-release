"""Review Weight v1 — 각 리뷰의 점수 계산 영향력.

w = w_min + (1-w_min) · [ (1-p_eff)^(ad_curve·exp_ad) · f_qual^exp_qual · f_src^exp_src · f_rev^exp_rev ] · f_time

설계 의도(스펙 §8 표 재현): p=0.8 → w≈0.09, p=0.5 → w≈0.34, p=0.2 → w≈0.70.
광고 가능성이 높은 리뷰도 실제 발생한 사건이므로 w_min(0.05)의 최소 영향력은 유지한다.
"""
from dataclasses import dataclass
from datetime import datetime

from ..config import ScoringConfig
from ..models import Review


@dataclass
class ReviewWeight:
    weight: float
    p_eff: float
    factors: dict[str, float]


def effective_ad_probability(analysis, ad_label: str | None, cfg: ScoringConfig) -> float:
    """ad_label(광고 ground truth)만 사용 — manipulation_label은 여기 영향 없음 (Phase 3A.1).

    신뢰도가 낮은 LLM 판단은 ad_prior로 수축한다."""
    if ad_label is not None:
        if ad_label not in cfg.label_values:
            raise ValueError(f"unknown ad label: {ad_label}")
        return cfg.label_values[ad_label]
    confidence = min(max(analysis.ad_confidence, 0.0), 1.0)
    p = confidence * analysis.ad_probability + (1 - confidence) * cfg.ad_prior
    return min(max(p, 0.0), 1.0)


def reviewer_factor(review: Review, cfg: ScoringConfig) -> float:
    count = review.reviewer_review_count
    if count is None:
        return cfg.reviewer_factor_unknown
    if count >= cfg.reviewer_high:
        return cfg.reviewer_factor_high
    if count >= cfg.reviewer_mid:
        return cfg.reviewer_factor_mid
    return cfg.reviewer_factor_low


def review_weight(
    review: Review,
    cfg: ScoringConfig,
    reference: datetime,
    duplicate: bool = False,
) -> ReviewWeight:
    assert review.analysis is not None, f"review {review.id} has no analysis"
    an = review.analysis
    p_eff = effective_ad_probability(an, review.manual_label, cfg)

    f_ad = (1.0 - p_eff) ** cfg.ad_curve
    qual_raw = cfg.qual_auth_share * an.authenticity + (1 - cfg.qual_auth_share) * an.specificity
    f_qual = cfg.qual_floor + (1 - cfg.qual_floor) * qual_raw
    f_src = cfg.source_weights.get(review.source, cfg.source_default_weight)
    f_rev = reviewer_factor(review, cfg)
    f_time = cfg.recency_factor(review.age_months(reference))

    core = (
        (f_ad ** cfg.exp_ad)
        * (f_qual ** cfg.exp_qual)
        * (f_src ** cfg.exp_src)
        * (f_rev ** cfg.exp_rev)
    )
    weight = cfg.w_min + (1 - cfg.w_min) * core * f_time
    if duplicate:
        weight *= cfg.dup_member_factor

    factors = {
        "p_eff": p_eff, "f_ad": f_ad, "f_qual": f_qual,
        "f_src": f_src, "f_rev": f_rev, "f_time": f_time,
    }
    return ReviewWeight(weight=weight, p_eff=p_eff, factors=factors)
