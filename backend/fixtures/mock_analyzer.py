"""목 ReviewAnalyzer — GLM 실연동 전 Phase 0 검증용.

패턴(ground truth)별로 GLM이 내줄 것으로 기대되는 분포를 시드 기반으로 재현한다.
Phase 3에서 GlmAnalyzer가 같은 ReviewAnalysis 스키마를 출력하면 그대로 교체된다.
"""
import random
from dataclasses import dataclass, field

from app.analysis import ReviewAnalysis, Signal


@dataclass(frozen=True)
class PatternProfile:
    ad: tuple[float, float]
    conf: tuple[float, float]
    auth: tuple[float, float]
    spec: tuple[float, float]
    local: tuple[float, float]
    repeat_p: float
    negative_p: float
    wait_p: float
    ad_signals: list[str] = field(default_factory=list)
    auth_signals: list[str] = field(default_factory=list)
    sentiment_mode: str = "mixed"  # enthusiast | mixed | casual | critical
    summary: str = ""


PROFILES: dict[str, PatternProfile] = {
    "ad_blog": PatternProfile(
        ad=(0.78, 0.92), conf=(0.70, 0.85), auth=(0.15, 0.35), spec=(0.45, 0.68), local=(0.05, 0.25),
        repeat_p=0.0, negative_p=0.0, wait_p=0.02,
        ad_signals=["catalog_listing", "all_positive_no_drawback", "template_style", "marketing_usp_repeat"],
        sentiment_mode="enthusiast",
        summary="카탈로그형 정보 나열과 전 항목 칭찬으로 프로모션성 패턴이 감지된 리뷰",
    ),
    "ad_map": PatternProfile(
        ad=(0.58, 0.78), conf=(0.60, 0.80), auth=(0.30, 0.50), spec=(0.35, 0.60), local=(0.10, 0.30),
        repeat_p=0.05, negative_p=0.0, wait_p=0.0,
        ad_signals=["all_positive_no_drawback", "template_style"],
        sentiment_mode="enthusiast",
        summary="전 항목 찬양형 짧은 리뷰. 광고 가능성이 다소 존재",
    ),
    "general_positive": PatternProfile(
        ad=(0.10, 0.30), conf=(0.70, 0.90), auth=(0.60, 0.85), spec=(0.40, 0.70), local=(0.30, 0.60),
        repeat_p=0.10, negative_p=0.20, wait_p=0.10,
        auth_signals=["specific_menu_eval", "negative_point"],
        sentiment_mode="mixed",
        summary="장단점이 혼재한 일반 방문 후기",
    ),
    "genuine_local": PatternProfile(
        ad=(0.03, 0.18), conf=(0.75, 0.95), auth=(0.85, 0.97), spec=(0.80, 0.97), local=(0.70, 0.95),
        repeat_p=0.55, negative_p=0.30, wait_p=0.30,
        auth_signals=["repeat_visit", "local_context", "specific_menu_eval", "price_detail", "long_term_patron"],
        sentiment_mode="mixed",
        summary="재방문·로컬 문맥·구체적 경험이 포함된 신뢰도 높은 로컬 리뷰",
    ),
    "genuine_positive": PatternProfile(
        ad=(0.05, 0.20), conf=(0.75, 0.92), auth=(0.80, 0.95), spec=(0.70, 0.92), local=(0.40, 0.80),
        repeat_p=0.20, negative_p=0.35, wait_p=0.20,
        auth_signals=["specific_menu_eval", "negative_point", "wait_time"],
        sentiment_mode="mixed",
        summary="구체적 메뉴 평가와 단점이 함께 있는 실방문 후기",
    ),
    "casual_short": PatternProfile(
        ad=(0.10, 0.35), conf=(0.50, 0.80), auth=(0.50, 0.80), spec=(0.05, 0.25), local=(0.30, 0.60),
        repeat_p=0.05, negative_p=0.0, wait_p=0.0,
        auth_signals=[],
        sentiment_mode="casual",
        summary="정보량이 적은 짧은 리뷰. 광고 신호는 없으나 근거도 부족",
    ),
    "tourist_casual": PatternProfile(
        ad=(0.10, 0.30), conf=(0.60, 0.85), auth=(0.60, 0.85), spec=(0.30, 0.60), local=(0.02, 0.15),
        repeat_p=0.0, negative_p=0.15, wait_p=0.10,
        auth_signals=[],
        sentiment_mode="casual",
        summary="관광 목격 중심 리뷰. 로컬 성격은 낮음",
    ),
    "viral_tourist": PatternProfile(
        ad=(0.25, 0.50), conf=(0.55, 0.80), auth=(0.50, 0.80), spec=(0.35, 0.65), local=(0.02, 0.12),
        repeat_p=0.0, negative_p=0.02, wait_p=0.20,
        ad_signals=["template_style"],
        auth_signals=["wait_time"],
        sentiment_mode="enthusiast",
        summary="SNS 바이럴 반응형 관광객 리뷰",
    ),
    "viral_dup": PatternProfile(
        ad=(0.42, 0.62), conf=(0.50, 0.75), auth=(0.45, 0.70), spec=(0.30, 0.55), local=(0.02, 0.10),
        repeat_p=0.0, negative_p=0.0, wait_p=0.0,
        ad_signals=["template_style", "marketing_usp_repeat"],
        sentiment_mode="enthusiast",
        summary="유사 문구가 반복 감지된 리뷰 (near-duplicate)",
    ),
    "nopo_old": PatternProfile(
        ad=(0.03, 0.15), conf=(0.70, 0.90), auth=(0.85, 0.97), spec=(0.60, 0.85), local=(0.60, 0.90),
        repeat_p=0.45, negative_p=0.25, wait_p=0.10,
        auth_signals=["long_term_patron", "local_context", "repeat_visit"],
        sentiment_mode="mixed",
        summary="장기 단골의 노포 리뷰. 신뢰도 높음",
    ),
    "enthusiastic_short": PatternProfile(
        ad=(0.10, 0.30), conf=(0.60, 0.85), auth=(0.70, 0.90), spec=(0.30, 0.60), local=(0.20, 0.50),
        repeat_p=0.05, negative_p=0.05, wait_p=0.10,
        auth_signals=[],
        sentiment_mode="casual",
        summary="짧지만 긍정적인 방문 후기",
    ),
    "critical_specific": PatternProfile(
        ad=(0.03, 0.15), conf=(0.80, 0.95), auth=(0.85, 0.97), spec=(0.80, 0.95), local=(0.50, 0.85),
        repeat_p=0.15, negative_p=0.90, wait_p=0.20,
        auth_signals=["negative_point", "specific_menu_eval", "price_detail", "wait_time"],
        sentiment_mode="critical",
        summary="구체적 불만이 담긴 신뢰도 높은 비판 리뷰",
    ),
}

_SENTIMENT_RANGES: dict[str, dict[str, tuple[float, float] | None]] = {
    "enthusiast": {
        "food": (0.80, 1.00), "service": (0.75, 0.95), "price": (0.70, 0.95),
        "atmosphere": (0.80, 1.00), "accessibility": (0.70, 0.95),
    },
    "mixed": {
        "food": (0.70, 0.95), "service": (0.50, 0.85), "price": (0.50, 0.85),
        "atmosphere": (0.50, 0.90), "accessibility": (0.50, 0.85),
    },
    "casual": {
        "food": (0.70, 0.95), "service": None, "price": None,
        "atmosphere": (0.60, 0.90), "accessibility": None,
    },
    "critical": {
        "food": (0.45, 0.70), "service": (0.20, 0.45), "price": (0.30, 0.55),
        "atmosphere": (0.40, 0.70), "accessibility": (0.40, 0.65),
    },
}


def mock_analyze(pattern: str, text: str, rng: random.Random) -> ReviewAnalysis:
    profile = PROFILES[pattern]
    u = rng.uniform

    sentiment = {}
    for key, rng_range in _SENTIMENT_RANGES[profile.sentiment_mode].items():
        sentiment[key] = round(u(*rng_range), 2) if rng_range else None

    quote = text[:24]
    ad_signals = [Signal(code=code, quote=quote) for code in profile.ad_signals]
    auth_signals = [Signal(code=code, quote=quote) for code in profile.auth_signals]

    specificity = round(u(*profile.spec), 2)
    negative = rng.random() < profile.negative_p

    return ReviewAnalysis(
        analyzer="mock-v1",
        prompt_version="mock-1",
        ad_probability=round(u(*profile.ad), 2),
        ad_confidence=round(u(*profile.conf), 2),
        authenticity=round(u(*profile.auth), 2),
        specificity=specificity,
        local_probability=round(u(*profile.local), 2),
        sentiment=sentiment,
        visit_context={
            "repeat_visit": rng.random() < profile.repeat_p,
            "wait_time_mentioned": rng.random() < profile.wait_p,
            "menu_specificity": specificity,
            "negative_points_present": negative,
        },
        ad_signals=ad_signals,
        authentic_signals=auth_signals,
        summary=profile.summary,
        flags={"insufficient_text": len(text) < 8},
    )
