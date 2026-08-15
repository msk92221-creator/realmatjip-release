"""Google Places API (New) HTTP 클라이언트 — Places API v1 기준.

인증: X-Goog-Api-Key 헤더
Field Mask: X-Goog-FieldMask 헤더로 필요한 필드만 요청 (스펙 §18)
"""
import time
from typing import Any

import httpx

BASE_URL = "https://places.googleapis.com/v1"

# 스펙 §18: MVP에서 필요한 최소 필드만 요청
SEARCH_FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.primaryType",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
])

DETAIL_FIELDS = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "primaryType",
    "rating",
    "userRatingCount",
    "googleMapsUri",
    "reviews",
    "reviews.rating",
    "reviews.text",
    "reviews.authorAttribution",
    "reviews.publishTime",
    "reviews.originalText",
])


class GooglePlacesError(Exception):
    """Google Places API 오류 — Backend 전체가 죽지 않게 한다 (스펙 §19)."""
    def __init__(self, message: str, status_code: int | None = None,
                 retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GooglePlacesClient:
    """Google Places API (New) 클라이언트 — Backend에서만 호출 (스펙 §2)."""

    def __init__(self, api_key: str, timeout: float = 15.0,
                 retry_delays: tuple[float, ...] = (1.0, 3.0),
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise GooglePlacesError("GOOGLE_PLACES_API_KEY가 설정되지 않았습니다")
        self.api_key = api_key
        self.retry_delays = retry_delays
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={
                "X-Goog-Api-Key": api_key,
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    def search_text(self, query: str, lat: float | None = None,
                    lng: float | None = None, radius_m: int = 5000,
                    max_results: int = 20, language: str = "ko") -> dict[str, Any]:
        """POST /v1/places:searchText — 텍스트 검색."""
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": language,
            "maxResultCount": min(max_results, 20),
        }
        if lat is not None and lng is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": min(radius_m, 50000),
                }
            }

        return self._request("POST", "/places:searchText",
                             field_mask=SEARCH_FIELDS, body=body)

    def get_place_detail(self, place_id: str, language: str = "ko") -> dict[str, Any]:
        """GET /v1/places/{place_id} — 상세 정보 + 리뷰 샘플."""
        return self._request("GET", f"/places/{place_id}",
                             field_mask=DETAIL_FIELDS,
                             params={"languageCode": language})

    def _request(self, method: str, path: str, field_mask: str,
                 body: dict | None = None, params: dict | None = None) -> dict[str, Any]:
        """공통 요청 — 429/5xx 재시도, 무한 retry 금지 (스펙 §20)."""
        url = f"{BASE_URL}{path}"
        # Places API (New) 표준 헤더: X-Goog-FieldMask (FieldMask 한 단어 — 하이픈 위치가 다르면 400)
        headers = {"X-Goog-FieldMask": field_mask}

        last_error: Exception | None = None
        for attempt in range(len(self.retry_delays) + 1):
            try:
                if method == "POST":
                    response = self._client.post(url, json=body, headers=headers)
                else:
                    response = self._client.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    return response.json()

                error_text = response.text[:300]

                # 스펙 §19: 오류 유형별 처리
                if response.status_code == 403:
                    raise GooglePlacesError(
                        f"API key 인증 실패 (403): {error_text}", 403, retryable=False)
                if response.status_code == 404:
                    raise GooglePlacesError(
                        f"Place를 찾을 수 없음 (404): {error_text}", 404, retryable=False)
                if response.status_code == 429:
                    # quota/rate limit — 재시도 (스펙 §20)
                    if attempt < len(self.retry_delays):
                        time.sleep(self.retry_delays[attempt])
                        last_error = GooglePlacesError(
                            f"Rate limit (429): {error_text}", 429, retryable=True)
                        continue
                    raise GooglePlacesError(
                        f"Quota 초과 (429): {error_text}", 429, retryable=False)
                if 500 <= response.status_code < 600:
                    if attempt < len(self.retry_delays):
                        time.sleep(self.retry_delays[attempt])
                        last_error = GooglePlacesError(
                            f"서버 오류 ({response.status_code}): {error_text}",
                            response.status_code, retryable=True)
                        continue
                    raise GooglePlacesError(
                        f"서버 오류 ({response.status_code}): {error_text}",
                        response.status_code, retryable=False)

                raise GooglePlacesError(
                    f"알 수 없는 오류 ({response.status_code}): {error_text}",
                    response.status_code, retryable=False)

            except httpx.TimeoutException:
                if attempt < len(self.retry_delays):
                    time.sleep(self.retry_delays[attempt])
                    last_error = GooglePlacesError(
                        "Network timeout", None, retryable=True)
                    continue
                raise GooglePlacesError("Network timeout", None, retryable=False)
            except httpx.HTTPError as exc:
                raise GooglePlacesError(f"Network 오류: {exc}", None, retryable=False)

        raise last_error or GooglePlacesError("Unknown error", None, retryable=False)

    def close(self):
        self._client.close()
