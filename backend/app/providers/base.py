"""Provider 공통 인터페이스와 모델 — 모든 provider가 이 추상에 맞춘다.

NormalizedReview 이후 pipeline(Dedup→Analyzer→Scoring)은
provider가 무엇이든 동일하게 동작해야 한다 (스펙 §7).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class ProviderRestaurant:
    """Provider가 반환하는 식당 정보 — 내부 Restaurant로 변환된다."""
    provider: str                    # "google_places" | "manual_import" | ...
    provider_place_id: str           # provider 고유 ID (예: google place_id)
    name: str
    formatted_address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    primary_type: str = ""           # provider 카테고리
    rating: float | None = None      # provider 자체 평점 (참고용)
    user_rating_count: int = 0       # provider 전체 리뷰 수
    provider_url: str = ""           # provider Maps/웹 링크
    provider_metadata: dict = field(default_factory=dict)  # provider 고유 필드 보존


@dataclass
class ProviderReview:
    """Provider가 반환하는 리뷰 — NormalizedReview(text_hash 계산 후)로 변환된다."""
    provider: str                    # source 필드와 동일
    provider_review_id: str = ""     # provider 고유 리뷰 ID
    provider_place_id: str = ""      # 소속 식당 ID
    rating: float | None = None
    text: str = ""
    author_name: str = ""            # attribution용
    author_url: str = ""             # attribution용
    published_at: datetime | None = None
    language: str = ""
    original_text: str = ""          # 번역 전 원문 (있으면)
    provider_metadata: dict = field(default_factory=dict)


@dataclass
class RestaurantMatchResult:
    """Google 식당을 기존 DB에 매칭한 결과 (스펙 §5)."""
    match_type: str                  # "exact_place_id" | "name_coords" | "name_address" | "no_match"
    matched_restaurant_id: str | None = None
    matched_name: str = ""
    distance_m: float | None = None  # 좌표 거리 (미터)
    confidence: float = 0.0          # 0~1
    provider_place_id: str = ""


class RestaurantProvider(Protocol):
    """식당 검색/발견 Provider — scoring/LLM 코드에 침투하지 않는다 (스펙 §1)."""
    provider_name: str

    def search_places(self, query: str, lat: float | None = None,
                      lng: float | None = None, radius_m: int = 5000,
                      max_results: int = 20) -> list[ProviderRestaurant]: ...

    def get_place(self, place_id: str) -> ProviderRestaurant | None: ...

    def get_reviews(self, place_id: str) -> list[ProviderReview]: ...


@dataclass
class ProviderImportPreview:
    """Provider Import Preview — DB 변경 없음 (스펙 §14)."""
    restaurant: ProviderRestaurant
    match: RestaurantMatchResult
    review_count: int = 0
    review_samples: list[ProviderReview] = field(default_factory=list)
    new_reviews: int = 0             # 중복 제외 실제 신규
    duplicates: int = 0
    existing_reviews: int = 0        # 기존 DB에 있는 이 식당 리뷰 수
    error: str | None = None
