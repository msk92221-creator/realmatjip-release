"""하위 점수(베이지안 수축) + Overall Score Version A/B."""
from dataclasses import dataclass, field

from ..config import ScoringConfig
from .bayes import shrunk_mean
from .signals import ManipulationDetail


@dataclass
class SubScores:
    rating_adjusted: float          # r01 (0~1)
    ad_free: float
    trust: float
    local: float
    repeat: float
    food: float | None
    value: float | None
    n_raw: int
    n_eff: float                    # Σw — 유효 리뷰 수
    evidence_strength: float        # 결정 #1: n_eff/(n_eff+C) — Overall 미반영, UI/설명용
    local_evidence: float           # Σw over local_prob ≥ threshold
    dataset_prior: float
    mean_p_eff: float               # 가중 평균 유효 광고확률 (표시/디버깅용)
    ad_share_07: float              # p_eff ≥ 0.7 리뷰 비율 (원시)


def trust_value(p_eff: float, authenticity: float, specificity: float, cfg: ScoringConfig) -> float:
    return (cfg.trust_ad_share * (1 - p_eff)
            + cfg.trust_auth_share * authenticity
            + cfg.trust_spec_share * specificity)


def sub_scores(
    r01s: list[float],
    rated_weights: list[float],      # 별점 있는 리뷰의 가중치 (r01s와 정렬)
    p_effs: list[float],
    trust_values: list[float],
    local_probs: list[float],
    repeat_flags: list[float],
    all_weights: list[float],        # 분석된 전체 리뷰의 가중치 (p_effs 등과 정렬)
    sentiments: dict[str, tuple[list[float], list[float]]],  # key → (values, weights)
    cfg: ScoringConfig,
    dataset_prior: float,
    n_raw: int,
    local_evidence: float,
) -> SubScores:
    n_eff = sum(all_weights)
    rating = shrunk_mean(r01s, rated_weights, dataset_prior, cfg.c_rating)
    ad_free = shrunk_mean([1 - p for p in p_effs], all_weights, cfg.prior_adfree, cfg.c_probability)
    trust = shrunk_mean(trust_values, all_weights, cfg.prior_trust, cfg.c_probability)
    local = shrunk_mean(local_probs, all_weights, cfg.prior_local, cfg.c_local)
    repeat = shrunk_mean(repeat_flags, all_weights, cfg.prior_repeat, cfg.c_repeat)

    food = value = None
    for key in ("food", "price"):
        vals, ws = sentiments.get(key, ([], []))
        if ws and sum(ws) >= 1.0:
            score = shrunk_mean(vals, ws, 0.6, cfg.c_probability)
            if key == "food":
                food = score
            else:
                value = score

    total_w = sum(all_weights) or 1.0
    mean_p = sum(p * w for p, w in zip(p_effs, all_weights)) / total_w
    ad_share = sum(1 for p in p_effs if p >= 0.7) / len(p_effs) if p_effs else 0.0

    return SubScores(
        rating_adjusted=rating, ad_free=ad_free, trust=trust, local=local,
        repeat=repeat, food=food, value=value, n_raw=n_raw, n_eff=n_eff,
        evidence_strength=n_eff / (n_eff + cfg.evidence_c),
        local_evidence=local_evidence, dataset_prior=dataset_prior,
        mean_p_eff=mean_p, ad_share_07=ad_share,
    )


@dataclass
class OverallResult:
    version: str
    score: float | None          # n_eff < min_n_eff → None ("데이터 부족")
    terms: list[tuple[str, float, float]] = field(default_factory=list)  # (항목, 신호값, 기여 점수)


def overall(
    sub: SubScores,
    consistency: float,
    longevity: float,
    manip: ManipulationDetail,
    cfg: ScoringConfig,
    version: str,
) -> OverallResult:
    if version not in cfg.overall_weights:
        raise ValueError(f"unknown overall version: {version}")
    if sub.n_eff < cfg.min_n_eff:
        return OverallResult(version=version, score=None, terms=[])

    w = cfg.overall_weights[version]
    values = {
        "rating": sub.rating_adjusted,
        "consistency": consistency,
        "repeat": sub.repeat,
        "local": sub.local,
        "longevity": longevity,
        "trust": sub.trust,
    }
    terms: list[tuple[str, float, float]] = [
        ("rating", values["rating"], w["rating"] * values["rating"]),
        ("consistency", values["consistency"], w["consistency"] * values["consistency"]),
        ("repeat", values["repeat"], w["repeat"] * values["repeat"]),
        ("local", values["local"], w["local"] * values["local"]),
        ("longevity", values["longevity"], w["longevity"] * values["longevity"]),
        ("trust", values["trust"], w["trust"] * values["trust"]),
        ("manipulation", manip.score, -cfg.manipulation_penalty_max * manip.score),
    ]
    score = min(max(sum(points for _, _, points in terms), 0.0), 100.0)
    return OverallResult(version=version, score=score, terms=terms)
