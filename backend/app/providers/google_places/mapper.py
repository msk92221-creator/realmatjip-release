"""Google Places 응답 → 내부 Provider 모델 매핑 (스펙 §4, §7).

Google 전용 데이터와 내부 공통 데이터를 구분하고,
provider_metadata JSON에 Google 고유 필드를 보존한다.
"""
import math
from datetime import datetime

from ..base import ProviderRestaurant, ProviderReview, RestaurantMatchResult


def parse_google_place(place: dict) -> ProviderRestaurant:
    """Google Places API 응답의 place 객체 → ProviderRestaurant."""
    location = place.get("location") or {}
    display = place.get("displayName") or {}

    return ProviderRestaurant(
        provider="google_places",
        provider_place_id=place.get("id", ""),
        name=display.get("text", ""),
        formatted_address=place.get("formattedAddress", ""),
        lat=float(location.get("latitude", 0.0)),
        lng=float(location.get("longitude", 0.0)),
        primary_type=place.get("primaryType", ""),
        rating=place.get("rating"),
        user_rating_count=place.get("userRatingCount", 0),
        provider_url=place.get("googleMapsUri", ""),
        # Google 고유 필드를 provider_metadata에 보존 (스펙 §4)
        provider_metadata={
            "primary_type": place.get("primaryType", ""),
            "types": place.get("types", []),
            "national_phone": place.get("nationalPhoneNumber", ""),
            "international_phone": place.get("internationalPhoneNumber", ""),
            "business_status": place.get("businessStatus", ""),
            "price_level": place.get("priceLevel", ""),
        },
    )


def parse_google_review(review: dict, place_id: str) -> ProviderReview:
    """Google Places 응답의 review 객체 → ProviderReview (스펙 §7)."""
    text_obj = review.get("text") or {}
    original_obj = review.get("originalText") or {}
    author = review.get("authorAttribution") or {}

    published_at = None
    if review.get("publishTime"):
        try:
            published_at = datetime.fromisoformat(
                review["publishTime"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    return ProviderReview(
        provider="google_places",
        provider_review_id=review.get("name", ""),  # "places/{id}/reviews/{review_id}"
        provider_place_id=place_id,
        rating=review.get("rating"),
        text=text_obj.get("text", ""),
        author_name=author.get("displayName", ""),
        author_url=author.get("uri", ""),
        published_at=published_at,
        language=text_obj.get("languageCode", ""),
        original_text=original_obj.get("text", ""),
        provider_metadata={
            # 스펙 §6: sample이 제한적임을 명시
            "source_sample_limited": True,
            # 스펙 §8: attribution 정보 보존
            "attribution": {
                "provider_name": "Google",
                "author_name": author.get("displayName", ""),
                "author_uri": author.get("uri", ""),
                "source_uri": author.get("photoUri", ""),
            },
            # 스펙 §9: 콘텐츠 소유/정책
            "content_owner": "google",
            "storage_policy": "sample_display_with_attribution",
        },
    )


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리 (미터)."""
    r = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize_name(name: str) -> str:
    """식당명 정규화 — 매칭용."""
    return (name or "").strip().lower().replace(" ", "").replace("(주)", "")


def match_restaurant(place: ProviderRestaurant, existing: list,
                     max_distance_m: float = 50.0) -> RestaurantMatchResult:
    """Google 식당 ↔ 기존 DB 식당 매칭 (스펙 §5).

    우선순위:
    1. google_place_id exact match (source_refs에 있으면)
    2. 정규화 name + 좌표 50m 이내
    3. 정규화 name + address 유사도
    """
    place_norm = normalize_name(place.name)

    # 1. google_place_id exact match
    for restaurant in existing:
        refs = (restaurant.raw_payload or {}).get("source_refs", {}) \
            if hasattr(restaurant, "raw_payload") else {}
        if isinstance(refs, dict) and refs.get("google_place_id") == place.provider_place_id:
            return RestaurantMatchResult(
                match_type="exact_place_id",
                matched_restaurant_id=restaurant.id,
                matched_name=restaurant.name,
                confidence=1.0,
                provider_place_id=place.provider_place_id,
            )

    # 2. name + 좌표 (50m 이내, config 관리)
    best_coord_match = None
    for restaurant in existing:
        if normalize_name(restaurant.name) == place_norm and restaurant.lat and place.lat:
            dist = haversine_m(place.lat, place.lng, restaurant.lat, restaurant.lng)
            if dist <= max_distance_m:
                if best_coord_match is None or dist < best_coord_match.distance_m:
                    best_coord_match = RestaurantMatchResult(
                        match_type="name_coords",
                        matched_restaurant_id=restaurant.id,
                        matched_name=restaurant.name,
                        distance_m=round(dist, 1),
                        confidence=0.9 if dist < 20 else 0.7,
                        provider_place_id=place.provider_place_id,
                    )

    if best_coord_match:
        return best_coord_match

    # 3. name + address 유사도 (간단한 포함 확인)
    for restaurant in existing:
        if normalize_name(restaurant.name) == place_norm:
            addr1 = (restaurant.address or "").lower().replace(" ", "")
            addr2 = (place.formatted_address or "").lower().replace(" ", "")
            if addr1 and addr2 and (addr1 in addr2 or addr2 in addr1):
                return RestaurantMatchResult(
                    match_type="name_address",
                    matched_restaurant_id=restaurant.id,
                    matched_name=restaurant.name,
                    confidence=0.6,
                    provider_place_id=place.provider_place_id,
                )

    # 4. 이름만 같고 좌표/주소 확인 불가 → 자동 merge 금지 (스펙 §5)
    return RestaurantMatchResult(
        match_type="no_match",
        confidence=0.0,
        provider_place_id=place.provider_place_id,
    )
