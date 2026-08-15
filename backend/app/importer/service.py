"""Import 서비스 — preview(dry run) / commit (스펙 §2).

preview는 DB를 건드리지 않는다. commit만 삽입하며, 원본 행(raw payload)을
reviews.raw_payload에 그대로 보존한다 (스펙 §1).
"""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from ..db.mappers import text_hash
from ..db.models import RestaurantORM, ReviewORM, utcnow

from .parser import ParsedReview, RowError, parse_payload


@dataclass
class ImportPreview:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    exact_duplicates: int = 0
    estimated_new_reviews: int = 0
    new_restaurants: int = 0
    matched_restaurants: int = 0
    errors: list[RowError] = field(default_factory=list)
    restaurants: list[dict] = field(default_factory=list)


@dataclass
class ImportCommit:
    inserted_restaurants: int = 0
    inserted_reviews: int = 0
    skipped_duplicates: int = 0
    invalid: int = 0
    errors: list[RowError] = field(default_factory=list)


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def _restaurant_id(name: str) -> str:
    digest = hashlib.sha1(_normalize_name(name).encode("utf-8")).hexdigest()[:8]
    return f"imp-{digest}"


def _plan(session, parsed: list[ParsedReview]) -> tuple[list, dict, dict]:
    """기존 식당 매칭(이름 정규화 기준) + exact duplicate(text_hash) 판정."""
    existing_restaurants = {
        _normalize_name(r.name): r
        for r in session.execute(select(RestaurantORM)).scalars()
    }
    existing_hashes = set(
        session.execute(select(ReviewORM.text_hash)).scalars()
    )
    seen_in_payload: set[str] = set()

    fresh = []
    matched_ids: dict[str, RestaurantORM] = {}
    new_names: dict[str, dict] = {}
    duplicates = 0
    for item in parsed:
        normalized = _normalize_name(item.restaurant_name)
        if normalized in existing_restaurants:
            matched_ids[normalized] = existing_restaurants[normalized]
        elif normalized not in new_names:
            new_names[normalized] = {
                "id": _restaurant_id(item.restaurant_name),
                "name": item.restaurant_name,
                "category": item.category,
                "address": item.address,
                "lat": item.lat,
                "lng": item.lng,
            }
        digest = text_hash(item.text)
        if digest in existing_hashes or digest in seen_in_payload:
            duplicates += 1
            continue
        seen_in_payload.add(digest)
        fresh.append((item, digest))
    return fresh, matched_ids, {"duplicates": duplicates, "new_names": new_names}


def preview_import(session, format: str, content: str) -> ImportPreview:
    parsed, errors = parse_payload(format, content)
    fresh, matched_ids, info = _plan(session, parsed)

    names = {_normalize_name(p.restaurant_name) for p in parsed}
    preview = ImportPreview(
        total=len(parsed) + len(errors),
        valid=len(parsed),
        invalid=len(errors),
        exact_duplicates=info["duplicates"],
        estimated_new_reviews=len(fresh),
        new_restaurants=len(names - set(matched_ids)),
        matched_restaurants=len(set(matched_ids) & names),
        errors=errors[:50],
    )
    for normalized in sorted(names):
        if normalized in matched_ids:
            restaurant = matched_ids[normalized]
            preview.restaurants.append({
                "id": restaurant.id, "name": restaurant.name, "status": "matched",
            })
        elif normalized in info["new_names"]:
            candidate = info["new_names"][normalized]
            preview.restaurants.append({
                "id": candidate["id"], "name": candidate["name"], "status": "new",
            })
    return preview


def commit_import(session, format: str, content: str) -> ImportCommit:
    parsed, errors = parse_payload(format, content)
    fresh, matched_ids, info = _plan(session, parsed)
    now = utcnow()

    inserted_restaurants = 0
    id_by_normalized: dict[str, RestaurantORM] = dict(matched_ids)
    for normalized, candidate in info["new_names"].items():
        restaurant = RestaurantORM(
            id=candidate["id"], name=candidate["name"],
            category=candidate.get("category") or "",
            address=candidate.get("address") or "",
            lat=candidate.get("lat") or 0.0,
            lng=candidate.get("lng") or 0.0,
        )
        session.add(restaurant)
        id_by_normalized[normalized] = restaurant
        inserted_restaurants += 1

    inserted_reviews = 0
    for item, digest in fresh:
        restaurant = id_by_normalized[_normalize_name(item.restaurant_name)]
        raw = dict(item.raw)
        raw["_import"] = {
            "format": format, "row": item.row,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "restaurant_name": item.restaurant_name,
        }
        session.add(ReviewORM(
            id=f"{restaurant.id}-r{digest[:12]}",
            restaurant_id=restaurant.id,
            source=item.source,
            source_review_id=item.source_review_id,
            source_url=item.source_url,
            reviewer_name=item.reviewer_name,
            reviewer_review_count=item.reviewer_review_count,
            rating=item.rating,
            text=item.text,
            text_hash=digest,
            raw_payload=raw,
            collected_at=now,
            reviewed_at=item.reviewed_at or now,
        ))
        inserted_reviews += 1

    session.commit()
    return ImportCommit(
        inserted_restaurants=inserted_restaurants,
        inserted_reviews=inserted_reviews,
        skipped_duplicates=info["duplicates"],
        invalid=len(errors),
        errors=errors[:50],
    )
