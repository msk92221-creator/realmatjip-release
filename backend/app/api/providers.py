"""Provider API — Google Places 검색/발견/Import (스펙 §17).

기존 /api/admin/import/*와 구조를 공유하되 Google 전용 코드를 섞지 않는다.
"""
import os
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request

from ..providers.base import ProviderImportPreview
from ..providers.google_places import GooglePlacesError, GooglePlacesProvider
from ..providers.google_places.import_service import (
    commit_google_import,
    preview_google_import,
)
from ..providers.google_places.mapper import parse_google_place, parse_google_review

router = APIRouter(prefix="/api/providers/google", tags=["providers"])


def _get_provider() -> GooglePlacesProvider:
    """GOOGLE_PLACES_API_KEY 확인 후 Provider 생성."""
    if not os.environ.get("GOOGLE_PLACES_API_KEY"):
        raise HTTPException(503, "GOOGLE_PLACES_API_KEY가 설정되지 않았습니다")
    return GooglePlacesProvider()


def _restaurant_to_dict(place) -> dict:
    return {
        "provider": place.provider,
        "place_id": place.provider_place_id,
        "name": place.name,
        "formatted_address": place.formatted_address,
        "lat": place.lat,
        "lng": place.lng,
        "primary_type": place.primary_type,
        "rating": place.rating,
        "user_rating_count": place.user_rating_count,
        "google_maps_url": place.provider_url,
        "provider_metadata": place.provider_metadata,
    }


@router.get("/search")
def google_search(request: Request, q: str, lat: float | None = None,
                  lng: float | None = None, radius: int = 5000, limit: int = 20):
    """Google Places 텍스트 검색 (스펙 §3)."""
    try:
        provider = _get_provider()
        places = provider.search_places(q, lat, lng, radius, limit)
        provider.close()
        return {
            "query": q,
            "count": len(places),
            "results": [_restaurant_to_dict(p) for p in places],
        }
    except GooglePlacesError as e:
        raise HTTPException(502, f"Google Places 오류: {e}")


@router.get("/place/{place_id}")
def google_place_detail(request: Request, place_id: str):
    """Google Place 상세 정보 + 리뷰 샘플."""
    try:
        provider = _get_provider()
        place = provider.get_place(place_id)
        reviews = provider.get_reviews(place_id)
        provider.close()

        if place is None:
            raise HTTPException(404, "Place를 찾을 수 없습니다")

        return {
            "place": _restaurant_to_dict(place),
            "review_count": len(reviews),
            "reviews": [{
                "provider": r.provider,
                "review_id": r.provider_review_id,
                "rating": r.rating,
                "text": r.text[:200],
                "author_name": r.author_name,
                "author_url": r.author_url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "source_sample_limited": True,
                "attribution": r.provider_metadata.get("attribution", {}),
            } for r in reviews],
        }
    except GooglePlacesError as e:
        raise HTTPException(502, f"Google Places 오류: {e}")


@router.post("/import/preview")
def google_import_preview(request: Request, body: dict):
    """Google Place Import Preview — DB 변경 없음 (스펙 §14).

    body: {"place_id": "...", "force_new": false}
    """
    place_id = body.get("place_id", "")
    force_new = body.get("force_new", False)
    if not place_id:
        raise HTTPException(400, "place_id required")

    try:
        provider = _get_provider()
        place = provider.get_place(place_id)
        if place is None:
            provider.close()
            raise HTTPException(404, "Place를 찾을 수 없습니다")
        reviews = provider.get_reviews(place_id)
        provider.close()
    except GooglePlacesError as e:
        raise HTTPException(502, f"Google Places 오류: {e}")

    with request.app.state.session_factory() as session:
        preview = preview_google_import(session, place, reviews)

    return {
        "restaurant": _restaurant_to_dict(preview.restaurant),
        "match": {
            "match_type": preview.match.match_type,
            "matched_restaurant_id": preview.match.matched_restaurant_id,
            "matched_name": preview.match.matched_name,
            "distance_m": preview.match.distance_m,
            "confidence": preview.match.confidence,
        },
        "review_count": preview.review_count,
        "new_reviews": preview.new_reviews,
        "duplicates": preview.duplicates,
        "existing_reviews": preview.existing_reviews,
        "review_samples": [{
            "rating": r.rating,
            "text": r.text[:200],
            "author_name": r.author_name,
        } for r in preview.review_samples],
    }


@router.post("/import/commit")
def google_import_commit(request: Request, body: dict):
    """Google Place Import 실행 (스펙 §15~§16).

    body: {"place_id": "...", "force_new": false}
    """
    place_id = body.get("place_id", "")
    force_new = body.get("force_new", False)
    if not place_id:
        raise HTTPException(400, "place_id required")

    try:
        provider = _get_provider()
        place = provider.get_place(place_id)
        if place is None:
            provider.close()
            raise HTTPException(404, "Place를 찾을 수 없습니다")
        reviews = provider.get_reviews(place_id)
        provider.close()
    except GooglePlacesError as e:
        raise HTTPException(502, f"Google Places 오류: {e}")

    with request.app.state.session_factory() as session:
        result = commit_google_import(session, place, reviews, force_new=force_new)

    return {
        "restaurant_id": result.restaurant_id,
        "restaurant_name": result.restaurant_name,
        "action": result.action,
        "inserted_reviews": result.inserted_reviews,
        "skipped_duplicates": result.skipped_duplicates,
        "review_samples_total": result.review_samples_total,
        "google_rating": place.rating,
        "google_rating_count": place.user_rating_count,
    }
