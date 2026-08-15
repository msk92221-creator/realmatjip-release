"""식당 레벨 신호 — 리뷰 내용(광고 가능성)과 분리된 메타데이터만 사용해 이중처벌을 방지한다.

- consistency: 플랫폼별 평점 일관성 (크로스 플랫폼 검증)
- manipulation: 리뷰 폭발(burst) + 중복(dup) — 원시 등록 건수 기준
- longevity: 여러 해에 걸친 안정적 평가 (노포 보상)
"""
from dataclasses import dataclass
from datetime import datetime

from ..config import ScoringConfig
from ..models import DAYS_PER_MONTH, Review
from .bayes import shrunk_mean


@dataclass
class PlatformStat:
    source: str
    n_reviews: int
    sum_w: float
    shrunk_rating: float  # r01 scale (0~1)


def platform_stats(
    reviews: list[Review],
    weights: dict[str, float],
    dup_member_ids: set[str],
    dataset_prior: float,
    cfg: ScoringConfig,
) -> list[PlatformStat]:
    """플랫폼 검증 게이트 (결정 #5): 중복 리뷰를 제외한 상태에서

      unique_review_count ≥ platform_min_unique_reviews
      AND Σ(유효 가중치) ≥ platform_min_effective_weight

    을 모두 충족하는 플랫폼만 통계에 포함한다. 저품질/광고/중복 리뷰가 많다는
    이유만으로 검증 조건을 통과하지 않게 하기 위한 이중 게이트이며,
    플랫폼 평점 자체도 중복을 제외한 리뷰로만 계산한다.
    """
    by_source: dict[str, list[Review]] = {}
    for r in reviews:
        if r.id in dup_member_ids:
            continue
        by_source.setdefault(r.source, []).append(r)

    stats = []
    for source, group in by_source.items():
        values = [r.r01 for r in group if r.r01 is not None]
        ws = [weights[r.id] for r in group if r.r01 is not None]
        if len(group) < cfg.platform_min_unique_reviews or not values:
            continue
        sum_w = sum(ws)
        if sum_w < cfg.platform_min_effective_weight:
            continue
        stats.append(PlatformStat(
            source=source, n_reviews=len(group), sum_w=sum_w,
            shrunk_rating=shrunk_mean(values, ws, dataset_prior, cfg.c_platform),
        ))
    return stats


def consistency(stats: list[PlatformStat], cfg: ScoringConfig) -> float:
    """플랫폼 간 평점 편차가 작을수록 1에 가까워짐. 검증 불가(k≤1)면 낮은 중립값."""
    if len(stats) <= 1:
        return cfg.consistency_single_platform
    mean = sum(s.shrunk_rating for s in stats) / len(stats)
    sd = (sum((s.shrunk_rating - mean) ** 2 for s in stats) / len(stats)) ** 0.5
    base = max(0.0, 1.0 - sd / cfg.consistency_sd_scale)
    factor = cfg.consistency_two_platform_factor if len(stats) == 2 else 1.0
    return min(base * factor, 1.0)


@dataclass
class ManipulationDetail:
    score: float
    burst01: float
    dup01: float
    peak_month_count: int
    median_month_count: float
    active_months: int


def manipulation(reviews: list[Review], dup_member_ids: set[str], cfg: ScoringConfig) -> ManipulationDetail:
    """폭발: 활성 월(리뷰 ≥1) 등록 건수의 중앙값 대비 최대 월 배수. 원시 건수 기준 —

    가중치를 이미 낮춘 리뷰가 폭발 감지에서도 보이지 않으면 조작 탐지가 무력화되므로.
    바이럴 ≠ 광고이므로 감점은 manipulation_penalty_max로 상한.
    """
    monthly: dict[str, int] = {}
    for r in reviews:
        key = f"{r.reviewed_at.year}-{r.reviewed_at.month:02d}"
        monthly[key] = monthly.get(key, 0) + 1

    counts = sorted(monthly.values())
    if not counts:
        return ManipulationDetail(0.0, 0.0, 0.0, 0, 0.0, 0)
    n = len(counts)
    median = counts[n // 2] if n % 2 else (counts[n // 2 - 1] + counts[n // 2]) / 2
    baseline = max(float(median), cfg.burst_min_baseline)
    peak = counts[-1]
    ratio = peak / baseline
    burst01 = max(0.0, min((ratio - cfg.burst_floor_ratio) / cfg.burst_span, 1.0))

    dup01 = len(dup_member_ids) / len(reviews) if reviews else 0.0
    score = min(cfg.manip_burst_share * burst01 + cfg.manip_dup_share * dup01, 1.0)
    return ManipulationDetail(score, burst01, dup01, peak, baseline, n)


def longevity(
    reviews: list[Review],
    weights: dict[str, float],
    cfg: ScoringConfig,
    reference: datetime,
) -> float:
    """연도 span(상한 4년) × 연도별 평점 안정성.

    안정성은 실제 연도별 가중평균의 (근거 가중) sd로 판정한다. 수축 평균을 쓰면
    근거가 적은 해가 사전확률로 수렴해 sd≈0, '증거 적은 식당이 더 안정적'이라는
    역보상이 생긴다(Phase 0 발견).
    """
    first = min(r.reviewed_at for r in reviews)
    last = max(r.reviewed_at for r in reviews)
    span_years = (last - first).days / 365.0
    span_factor = min(span_years / cfg.longevity_span_cap_years, 1.0)

    by_year: dict[int, list[Review]] = {}
    for r in reviews:
        if r.r01 is not None:
            by_year.setdefault(r.reviewed_at.year, []).append(r)

    yearly: list[tuple[float, float]] = []  # (연도 가중평균, 연도 근거 가중치)
    for group in by_year.values():
        ws = [weights[r.id] for r in group]
        total = sum(ws)
        if total >= cfg.longevity_min_year_weight:
            mean = sum(r.r01 * w for r, w in zip(group, ws)) / total
            yearly.append((mean, total))

    if len(yearly) >= 2:
        total = sum(w for _, w in yearly)
        mean = sum(m * w for m, w in yearly) / total
        variance = sum(w * (m - mean) ** 2 for m, w in yearly) / total
        stability = max(0.0, 1.0 - variance**0.5 / cfg.longevity_sd_scale)
    else:
        stability = cfg.longevity_weak_evidence_stability
    return span_factor * stability


def repeat_share(reviews: list[Review], weights: dict[str, float]) -> float:
    """재방문 언급 리뷰의 가중 비율 (원시). 베이지안 수축은 호출자가 적용."""
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    flagged = sum(
        w for r, w in zip(reviews, (weights[r.id] for r in reviews))
        if r.analysis is not None and r.analysis.visit_context.get("repeat_visit") is True
    )
    return flagged / total


def months_between(a: datetime, b: datetime) -> float:
    return abs((a - b).days) / DAYS_PER_MONTH
