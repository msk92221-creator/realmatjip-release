"""Google Places Import — Preview/Commit (스펙 §13~§16).

기존 manual import와 동일한 preview→commit 구조.
Google에서 가져온 리뷰는 source=google_places + source_sample_limited=true.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from ...db.mappers import text_hash
from ...db.models import RestaurantORM, ReviewORM, utcnow

from ..base import ProviderImportPreview, ProviderRestaurant, ProviderReview, RestaurantMatchResult
from .mapper import match_restaurant


@dataclass
class GoogleImportCommit:
    """Import Commit 결과."""
    restaurant_id: str = ""
    restaurant_name: str = ""
    action: str = ""                 # "created" | "linked" | "skipped"
    inserted_reviews: int = 0
    skipped_duplicates: int = 0
    review_samples_total: int = 0
    error: str | None = None


def _google_restaurant_id(place_id: str) -> str:
    return f"gp-{hashlib.sha1(place_id.encode()).hexdigest()[:12]}"


def preview_google_import(session, place: ProviderRestaurant,
                           reviews: list[ProviderReview]) -> ProviderImportPreview:
    """Google Place + 리뷰 샘플의 Import Preview — DB 변경 없음 (스펙 §14)."""
    existing = list(session.execute(select(RestaurantORM)).scalars())
    match = match_restaurant(place, existing)

    # 리뷰 중복 확인 (같은 식당 내 text_hash 기준)
    if match.matched_restaurant_id:
        existing_hashes = set(
            session.execute(
                select(ReviewORM.text_hash).where(
                    ReviewORM.restaurant_id == match.matched_restaurant_id)
            ).scalars()
        )
    else:
        existing_hashes = set()

    seen_in_batch: set[str] = set()
    new_count = 0
    dup_count = 0
    for review in reviews:
        if not review.text.strip():
            continue
        h = text_hash(review.text)
        if h in existing_hashes or h in seen_in_batch:
            dup_count += 1
        else:
            seen_in_batch.add(h)
            new_count += 1

    # 기존 식당의 리뷰 수
    existing_review_count = 0
    if match.matched_restaurant_id:
        existing_review_count = len(
            session.execute(
                select(ReviewORM.id).where(ReviewORM.restaurant_id == match.matched_restaurant_id)
            ).scalars().all()
        )

    return ProviderImportPreview(
        restaurant=place,
        match=match,
        review_count=len([r for r in reviews if r.text.strip()]),
        review_samples=reviews[:5],  # preview에는 최대 5개만 표시
        new_reviews=new_count,
        duplicates=dup_count,
        existing_reviews=existing_review_count,
    )


def commit_google_import(session, place: ProviderRestaurant,
                          reviews: list[ProviderReview],
                          force_new: bool = False) -> GoogleImportCommit:
    """Google Place Import — 식당 생성/연결 + 리뷰 삽입 (스펙 §15~§16).

    force_new=True면 기존 매칭을 무시하고 신규 생성 (수동 override).
    """
    existing = list(session.execute(select(RestaurantORM)).scalars())
    match = match_restaurant(place, existing)

    # 식당 처리
    if match.matched_restaurant_id and not force_new:
        restaurant = session.get(RestaurantORM, match.matched_restaurant_id)
        action = "linked"
        # 기존 식당에 google_place_id 기록 (스펙 §16)
        raw = dict(restaurant.provider_metadata or {})
        refs = raw.get("source_refs", {})
        if isinstance(refs, dict):
            refs["google_place_id"] = place.provider_place_id
        else:
            refs = {"google_place_id": place.provider_place_id}
        raw["source_refs"] = refs
        raw["google_places_metadata"] = place.provider_metadata
        restaurant.provider_metadata = raw
    else:
        restaurant_id = _google_restaurant_id(place.provider_place_id)
        # 같은 place_id로 이미 생성된 경우 재사용
        existing_by_id = session.get(RestaurantORM, restaurant_id)
        if existing_by_id:
            restaurant = existing_by_id
            action = "linked"
        else:
            restaurant = RestaurantORM(
                id=restaurant_id,
                name=place.name,
                category=place.primary_type or "",
                address=place.formatted_address,
                lat=place.lat,
                lng=place.lng,
            )
            restaurant.provider_metadata = {
                "source_refs": {"google_place_id": place.provider_place_id},
                "google_places_metadata": place.provider_metadata,
                "provider": "google_places",
                "google_rating": place.rating,
                "google_rating_count": place.user_rating_count,
                "google_maps_url": place.provider_url,
            }
            session.add(restaurant)
            action = "created"

    # 리뷰 삽입
    existing_hashes = set(
        session.execute(
            select(ReviewORM.text_hash).where(ReviewORM.restaurant_id == restaurant.id)
        ).scalars()
    )

    inserted = 0
    skipped = 0
    session.flush()  # restaurant.id 확보

    for review in reviews:
        if not review.text.strip():
            continue
        h = text_hash(review.text)
        if h in existing_hashes:
            skipped += 1
            continue
        existing_hashes.add(h)

        raw_payload = {
            "provider": "google_places",
            "provider_review_id": review.provider_review_id,
            "author_name": review.author_name,
            "author_url": review.author_url,
            "language": review.language,
            "original_text": review.original_text,
            "google_place_id": place.provider_place_id,
            # 스펙 §6: sample 제한 표시
            "source_sample_limited": True,
            # 스펙 §8: provenance
            "collected_at": utcnow().isoformat(),
            "provider_metadata": review.provider_metadata,
        }

        review_id = f"{restaurant.id}-r{h[:12]}"
        session.add(ReviewORM(
            id=review_id,
            restaurant_id=restaurant.id,
            source="google_places",
            source_review_id=review.provider_review_id or None,
            source_url=review.author_url or place.provider_url,
            reviewer_name=review.author_name or None,
            rating=review.rating,
            text=review.text,
            text_hash=h,
            raw_payload=raw_payload,
            collected_at=utcnow(),
            reviewed_at=review.published_at or utcnow(),
        ))
        inserted += 1

    session.commit()
    return GoogleImportCommit(
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        action=action,
        inserted_reviews=inserted,
        skipped_duplicates=skipped,
        review_samples_total=len([r for r in reviews if r.text.strip()]),
    )
