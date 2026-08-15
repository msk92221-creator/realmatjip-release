"""데이터셋 스코어링 오케스트레이션.

score_dataset: 전체 리뷰로 empirical prior(μ_r) 계산 → 식당별
중복 마킹 → 리뷰 가중치 → 하위점수/신호 → Overall A/B.
LLM 분석이 없는 리뷰는 스킵 (분석 완료 후 스코어링이 원칙).
"""
from dataclasses import dataclass, field
from datetime import datetime

from ..config import ScoringConfig
from ..models import Restaurant, Review
from .duplicates import mark_duplicates
from .scores import OverallResult, SubScores, overall, sub_scores, trust_value
from .signals import (
    ManipulationDetail,
    PlatformStat,
    consistency,
    longevity,
    manipulation,
    platform_stats,
)
from .weights import review_weight


@dataclass
class RestaurantResult:
    restaurant: Restaurant
    sub: SubScores
    consistency: float
    longevity: float
    manipulation: ManipulationDetail
    overall_a: OverallResult
    overall_b: OverallResult
    platforms: list[PlatformStat] = field(default_factory=list)
    dup_count: int = 0
    local_badge: bool = False

    def score(self, version: str) -> float | None:
        return self.overall_a.score if version == "A" else self.overall_b.score


def dataset_prior(reviews: list[Review], cfg: ScoringConfig) -> float:
    """전체 리뷰의 r01 평균 — 베이지안 사전확률 μ_r."""
    values = [r.r01 for r in reviews if r.r01 is not None]
    if not values:
        return cfg.default_dataset_prior
    return sum(values) / len(values)


def score_restaurant(
    restaurant: Restaurant,
    reviews: list[Review],
    cfg: ScoringConfig,
    reference: datetime,
    prior_r: float,
) -> RestaurantResult:
    own = [r for r in reviews if r.restaurant_id == restaurant.id and r.analysis is not None]
    dup_map = mark_duplicates(own, cfg)

    all_weights: list[float] = []
    rated_weights: list[float] = []
    r01s: list[float] = []
    p_effs: list[float] = []
    trust_values: list[float] = []
    local_probs: list[float] = []
    repeat_flags: list[float] = []
    sentiment_lists: dict[str, tuple[list[float], list[float]]] = {
        k: ([], []) for k in ("food", "service", "price", "atmosphere", "accessibility")
    }
    weights: dict[str, float] = {}
    local_evidence = 0.0

    for r in own:
        rw = review_weight(r, cfg, reference, duplicate=(r.id in dup_map))
        weights[r.id] = rw.weight
        an = r.analysis
        all_weights.append(rw.weight)
        p_effs.append(rw.p_eff)
        trust_values.append(trust_value(rw.p_eff, an.authenticity, an.specificity, cfg))
        local_probs.append(an.local_probability)
        repeat_flags.append(1.0 if an.visit_context.get("repeat_visit") is True else 0.0)
        if an.local_probability >= cfg.local_evidence_threshold:
            local_evidence += rw.weight
        if r.r01 is not None:
            r01s.append(r.r01)
            rated_weights.append(rw.weight)
            for key, (vals, ws) in sentiment_lists.items():
                value = an.sentiment.get(key)
                if value is not None:
                    vals.append(value)
                    ws.append(rw.weight)

    sub = sub_scores(
        r01s=r01s,
        rated_weights=rated_weights,
        p_effs=p_effs,
        trust_values=trust_values,
        local_probs=local_probs,
        repeat_flags=repeat_flags,
        all_weights=all_weights,
        sentiments=sentiment_lists,
        cfg=cfg,
        dataset_prior=prior_r,
        n_raw=len(own),
        local_evidence=local_evidence,
    )
    stats = platform_stats(own, weights, set(dup_map.keys()), prior_r, cfg)
    manip = manipulation(own, set(dup_map.keys()), cfg)
    # 조작 위험이 만드는 인위적 플랫폼 일관성은 상호 검증으로 인정하지 않는다.
    cons = consistency(stats, cfg) * (1 - cfg.consistency_manip_discount * manip.score)
    long_ = longevity(own, weights, cfg, reference)
    overall_a = overall(sub, cons, long_, manip, cfg, "A")
    overall_b = overall(sub, cons, long_, manip, cfg, "B")

    return RestaurantResult(
        restaurant=restaurant, sub=sub, consistency=cons, longevity=long_,
        manipulation=manip, overall_a=overall_a, overall_b=overall_b,
        platforms=stats, dup_count=len(dup_map),
        local_badge=local_evidence >= cfg.local_evidence_min,
    )


def score_dataset(
    restaurants: list[Restaurant],
    reviews: list[Review],
    cfg: ScoringConfig,
    reference: datetime,
) -> list[RestaurantResult]:
    prior_r = dataset_prior(reviews, cfg)
    return [score_restaurant(rest, reviews, cfg, reference, prior_r) for rest in restaurants]


def rank_by(results: list[RestaurantResult], version: str = "A") -> list[RestaurantResult]:
    """점수 내림차순. 점수 없음(데이터 부족)은 항상 하단."""

    def key(res: RestaurantResult):
        score = res.score(version)
        return (score is not None, score if score is not None else -1.0)

    return sorted(results, key=key, reverse=True)


def naive_ranking(
    restaurants: list[Restaurant], reviews: list[Review]
) -> list[tuple[Restaurant, float, int]]:
    """광고 감점 전 단순 별점 평균 순위 (비교 기준선)."""
    out: list[tuple[Restaurant, float, int]] = []
    for rest in restaurants:
        values = [r.r01 for r in reviews if r.restaurant_id == rest.id and r.r01 is not None]
        mean = sum(values) / len(values) if values else 0.0
        out.append((rest, mean, len(values)))
    return sorted(out, key=lambda x: x[1], reverse=True)
