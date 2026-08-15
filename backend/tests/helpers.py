"""테스트용 리뷰/분석 팩토리."""
from datetime import datetime, timedelta

from app.analysis import ReviewAnalysis
from app.models import Restaurant, Review

REFERENCE = datetime(2026, 8, 15, 12, 0)

# 기본 텍스트는 rid 기반으로 단어를 바꿔 준다 — 모든 리뷰가 같은 텍스트면
# 중복 탐지가 발동해 가중치 테스트가 왜곡된다.
_VARIANTS = ["물냉면", "비빔냉면", "만두", "된장찌개", "김치찜", "제육볶음", "순두부", "갈비찜", "순대국", "잔치국수"]


def _default_text(rid: str) -> str:
    dish = _VARIANTS[sum(ord(c) for c in rid) % len(_VARIANTS)]
    return f"구체적인 방문 경험 리뷰입니다. {dish} 맛이 좋았고 양도 적당했습니다. 다음에 또 오려고요."


def make_analysis(
    ad: float = 0.10, conf: float = 0.90, auth: float = 0.85, spec: float = 0.85,
    local: float = 0.50, repeat: bool | None = None, pseudo: float | None = None,
    negative: bool = False,
) -> ReviewAnalysis:
    return ReviewAnalysis(
        analyzer="test", prompt_version="t",
        ad_probability=ad, ad_confidence=conf, authenticity=auth, specificity=spec,
        local_probability=local,
        sentiment={"food": 0.8, "service": 0.7, "price": 0.7, "atmosphere": 0.7, "accessibility": 0.7},
        visit_context={
            "repeat_visit": repeat, "wait_time_mentioned": False,
            "menu_specificity": spec, "negative_points_present": negative,
        },
        pseudo_rating=pseudo, summary="", flags={"insufficient_text": False},
    )


def make_review(
    rid: str, rest: str = "r1", source: str = "google_places", rating: float | None = 4.5,
    days: int = 10, text: str | None = None, rcount: int | None = 50,
    analysis: ReviewAnalysis | None = None, label: str | None = None,
) -> Review:
    return Review(
        id=rid, restaurant_id=rest, source=source, rating=rating,
        text=text or _default_text(rid),
        reviewed_at=REFERENCE - timedelta(days=days),
        reviewer_review_count=rcount,
        manual_label=label,
        analysis=analysis or make_analysis(),
    )


def make_restaurant(rid: str = "r1", name: str = "테스트식당") -> Restaurant:
    return Restaurant(id=rid, name=name, category="한식", lat=37.5, lng=127.0)
