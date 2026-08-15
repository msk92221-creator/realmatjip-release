"""리뷰 분석 결과 도메인 모델 — mock/LLM 공통 출력 스키마."""
from dataclasses import dataclass, field
from enum import Enum


class AdSignal(str, Enum):
    EXPLICIT_SPONSORSHIP = "explicit_sponsorship"
    CATALOG_LISTING = "catalog_listing"
    ALL_POSITIVE = "all_positive_no_drawback"
    MARKETING_USP_REPEAT = "marketing_usp_repeat"
    TEMPLATE_STYLE = "template_style"
    CTA_OUTLINK = "cta_outlink"
    PHOTO_PROMO = "photo_promo"


class AuthenticSignal(str, Enum):
    REPEAT_VISIT = "repeat_visit"
    SPECIFIC_MENU_EVAL = "specific_menu_eval"
    NEGATIVE_POINT = "negative_point"
    WAIT_TIME = "wait_time"
    PRICE_DETAIL = "price_detail"
    LOCAL_CONTEXT = "local_context"
    VISIT_TIMING = "visit_timing"
    LONG_TERM_PATRON = "long_term_patron"


@dataclass
class Signal:
    code: str
    quote: str  # 리뷰 원문에서 온 verbatim 인용 (검증 계층이 존재 확인)


@dataclass
class ReviewAnalysis:
    analyzer: str                 # 예: "glm-4.7", "rules_v1", "mock"
    prompt_version: str
    ad_probability: float
    ad_confidence: float
    authenticity: float
    specificity: float
    local_probability: float
    sentiment: dict[str, float | None] = field(
        default_factory=lambda: {
            "food": None, "service": None, "price": None,
            "atmosphere": None, "accessibility": None,
        }
    )
    visit_context: dict[str, bool | float | None] = field(
        default_factory=lambda: {
            "repeat_visit": None, "wait_time_mentioned": None,
            "menu_specificity": None, "negative_points_present": None,
        }
    )
    ad_signals: list[Signal] = field(default_factory=list)
    authentic_signals: list[Signal] = field(default_factory=list)
    pseudo_rating: float | None = None  # 별점 없는 리뷰(블로그 등) 전용, 1~5
    summary: str = ""
    flags: dict[str, bool] = field(default_factory=lambda: {"insufficient_text": False})
