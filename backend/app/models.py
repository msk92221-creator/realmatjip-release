"""Normalized 데이터 모델. 모든 provider가 이 스키마로 변환한다."""
from dataclasses import dataclass
from datetime import datetime

from .analysis import ReviewAnalysis

DAYS_PER_MONTH = 30.44


@dataclass
class Restaurant:
    id: str
    name: str
    category: str
    lat: float
    lng: float
    address: str = ""


@dataclass
class Review:
    id: str
    restaurant_id: str
    source: str                      # google_places|naver_map|kakao_map|naver_blog|community|manual_import
    rating: float | None             # 1~5. 없으면 None
    text: str
    reviewed_at: datetime
    reviewer_review_count: int | None = None
    manual_label: str | None = None  # ad|ad_likely|ambiguous|normal — LLM보다 우선
    analysis: ReviewAnalysis | None = None
    duplicate_of: str | None = None  # near-dup 클러스터 대표 리뷰 id

    def age_months(self, reference: datetime) -> float:
        return max((reference - self.reviewed_at).days, 0) / DAYS_PER_MONTH

    @property
    def r01(self) -> float | None:
        """1~5 평점을 0~1로 정규화. 별점 없는 리뷰는 pseudo_rating 사용."""
        rating = self.rating
        if rating is None and self.analysis is not None:
            rating = self.analysis.pseudo_rating
        if rating is None:
            return None
        return (rating - 1.0) / 4.0
