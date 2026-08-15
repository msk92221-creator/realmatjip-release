"""GooglePlacesProvider — 식당 검색/발견 + 리뷰 샘플 (스펙 §2~§7).

Google 코드가 scoring, LLM analyzer, DB business logic에 침투하지 않게 한다.
이 Provider는 ProviderRestaurant/ProviderReview만 반환한다.
"""
import os
from typing import Any

from ..base import ProviderRestaurant, ProviderReview
from .client import GooglePlacesClient, GooglePlacesError
from .mapper import parse_google_place, parse_google_review


class GooglePlacesProvider:
    """Google Places API (New) 기반 식당 발견 Provider."""
    provider_name = "google_places"

    def __init__(self, api_key: str | None = None, transport=None, **client_kwargs):
        self._client = GooglePlacesClient(
            api_key=api_key or os.environ.get("GOOGLE_PLACES_API_KEY", ""),
            transport=transport,
            **client_kwargs,
        )

    def search_places(self, query: str, lat: float | None = None,
                      lng: float | None = None, radius_m: int = 5000,
                      max_results: int = 20) -> list[ProviderRestaurant]:
        """텍스트 검색 → 식당 후보 목록 (스펙 §3)."""
        response = self._client.search_text(query, lat, lng, radius_m, max_results)
        places = response.get("places", [])
        return [parse_google_place(p) for p in places]

    def get_place(self, place_id: str) -> ProviderRestaurant | None:
        """place_id로 상세 정보 조회."""
        try:
            response = self._client.get_place_detail(place_id)
            return parse_google_place(response)
        except GooglePlacesError as e:
            if e.status_code == 404:
                return None
            raise

    def get_reviews(self, place_id: str) -> list[ProviderReview]:
        """place_id의 리뷰 샘플 (제한적 — 전체가 아님, 스펙 §6)."""
        try:
            response = self._client.get_place_detail(place_id)
            reviews = response.get("reviews", [])
            return [parse_google_review(r, place_id) for r in reviews]
        except GooglePlacesError as e:
            if e.status_code == 404:
                return []
            raise

    def close(self):
        self._client.close()
