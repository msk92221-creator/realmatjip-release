"""Scoring 설정 — 모든 상수는 이 객체 하나로 관리한다 (결정 #6: magic number 금지).

v1 기본값은 Phase 0 시뮬레이션(시드 42)에서 확정한 provisional 값.
c_rating / duplicate_threshold는 후보군에 대한 민감도 리포트를 제공하며
실데이터가 쌓인 후 empirical calibration으로 확정한다.
"""
from dataclasses import dataclass, field

ALGORITHM_VERSION = "v0.1-phase0"

# (개월 상한, 가중치). 상한 초과(24개월+)는 recency_older_than_24m 적용.
RECENCY_TIERS: tuple[tuple[float, float], ...] = (
    (3.0, 1.00),
    (6.0, 0.90),
    (12.0, 0.80),
    (24.0, 0.65),
)

SOURCE_WEIGHTS: dict[str, float] = {
    "google_places": 1.00,
    "naver_map": 0.95,
    "kakao_map": 0.95,
    "manual_import": 0.90,
    "community": 0.85,
    "naver_blog": 0.80,
}

MANUAL_LABEL_VALUES: dict[str, float] = {
    "ad": 0.95,
    "likely_ad": 0.75,
    "ambiguous": 0.50,
    "normal": 0.05,
}

# 조작 ground truth — ad_probability에 영향 없음 (Phase 3A.1 분리 원칙)
MANIPULATION_LABELS = ("suspicious", "ambiguous", "normal")

# D6: A안(기본) / B안(평점 비중 축소, 신뢰·로컬 비중 확대)
OVERALL_WEIGHTS: dict[str, dict[str, float]] = {
    "A": {"rating": 55, "consistency": 12, "repeat": 8, "local": 8, "longevity": 7, "trust": 10},
    "B": {"rating": 45, "consistency": 14, "repeat": 10, "local": 10, "longevity": 8, "trust": 13},
}

# c_rating 후보 (결정 #3: 기본 10, 실데이터 확정 전 민감도 테스트 대상)
C_RATING_CANDIDATES: tuple[float, ...] = (6.0, 8.0, 10.0, 12.0)
# duplicate threshold 후보 (결정 #4)
DUPLICATE_THRESHOLD_CANDIDATES: tuple[float, ...] = (0.85, 0.87, 0.89, 0.91, 0.93, 0.95)


@dataclass
class ScoringConfig:
    algorithm_version: str = ALGORITHM_VERSION

    # ── 유효 광고확률 ──────────────────────────────────────────
    ad_prior: float = 0.30            # D5: 관측 prior로 교체 가능
    min_labeled_for_observed_prior: int = 30

    # ── review weight ─────────────────────────────────────────
    w_min: float = 0.05
    ad_curve: float = 2.5             # f_ad = (1-p)^ad_curve
    exp_ad: float = 0.70
    exp_qual: float = 0.20
    exp_src: float = 0.05
    exp_rev: float = 0.05
    qual_auth_share: float = 0.6      # f_qual 내 authenticity 비중 (나머지 specificity)
    qual_floor: float = 0.5
    recency_older_than_24m: float = 0.45
    dup_member_factor: float = 0.10
    reviewer_high: int = 20
    reviewer_mid: int = 5
    reviewer_factor_high: float = 1.0
    reviewer_factor_mid: float = 0.8
    reviewer_factor_low: float = 0.6
    reviewer_factor_unknown: float = 0.85
    source_default_weight: float = 0.90

    # ── trust 합성 (결정 #6: 코드에 박힌 0.6/0.3/0.1 분리) ────
    trust_ad_share: float = 0.6
    trust_auth_share: float = 0.3
    trust_spec_share: float = 0.1

    # ── 베이지안 수축 ──────────────────────────────────────────
    c_rating: float = 10.0            # 결정 #3: 후보 6/8/10/12
    c_platform: float = 2.0           # 크면 소수 플랫폼 평점이 사전확률로 수렴해 편차 소멸
    c_probability: float = 8.0
    c_local: float = 12.0
    c_repeat: float = 6.0
    prior_local: float = 0.35
    prior_adfree: float = 0.70
    prior_trust: float = 0.60
    prior_repeat: float = 0.08
    default_dataset_prior: float = 0.75

    # ── 근거 강도 (결정 #1: Overall 미반영, UI/explanation 전용) ─
    evidence_c: float = 8.0
    evidence_label_high: float = 0.65
    evidence_label_mid: float = 0.40

    # ── 식당 레벨 신호 ─────────────────────────────────────────
    # 결정 #5: 플랫폼 검증 게이트 — 중복 제외 리뷰 수와 유효 가중치를 모두 충족해야.
    # 저품질/광고/중복 리뷰가 많다는 이유만으로 검증 조건을 통과하지 않게 한다.
    platform_min_unique_reviews: int = 3
    platform_min_effective_weight: float = 1.5
    consistency_sd_scale: float = 0.25
    consistency_two_platform_factor: float = 0.85
    consistency_single_platform: float = 0.45
    consistency_manip_discount: float = 1.0
    burst_floor_ratio: float = 2.5
    burst_span: float = 10.0
    burst_min_baseline: float = 2.0
    manip_burst_share: float = 0.55
    manip_dup_share: float = 0.45
    longevity_span_cap_years: float = 4.0
    longevity_sd_scale: float = 0.15
    longevity_min_year_weight: float = 0.8
    longevity_weak_evidence_stability: float = 0.5

    # ── 게이트 / 배지 / 페널티 ─────────────────────────────────
    min_n_eff: float = 2.0
    local_evidence_threshold: float = 0.60
    local_evidence_min: float = 2.0
    manipulation_penalty_max: float = 12.0

    # ── near-duplicate (결정 #4: 후보 0.85~0.95 민감도 테스트) ─
    duplicate_threshold: float = 0.89
    duplicate_min_length: int = 16
    dup_ngram_size: int = 2

    source_weights: dict[str, float] = field(
        default_factory=lambda: dict(SOURCE_WEIGHTS)
    )
    label_values: dict[str, float] = field(
        default_factory=lambda: dict(MANUAL_LABEL_VALUES)
    )
    overall_weights: dict[str, dict[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in OVERALL_WEIGHTS.items()}
    )

    def recency_factor(self, age_months: float) -> float:
        for bound, weight in RECENCY_TIERS:
            if age_months <= bound:
                return weight
        return self.recency_older_than_24m

    def evidence_label(self, strength: float) -> str:
        if strength >= self.evidence_label_high:
            return "높음"
        if strength >= self.evidence_label_mid:
            return "보통"
        return "낮음"


def observed_ad_prior(labels: list[str | None], cfg: ScoringConfig) -> float | None:
    """수동 라벨이 min_labeled_for_observed_prior개 이상이면 평균 유효 광고확률을 prior로 반환.

    라벨된 리뷰의 기대 ad_probability를 관측 기저율로 사용한다.
    부족하면 None → 기존 cfg.ad_prior 유지.
    """
    values = [cfg.label_values[l] for l in labels if l in cfg.label_values]
    if len(values) < cfg.min_labeled_for_observed_prior:
        return None
    return sum(values) / len(values)
