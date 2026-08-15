"""Import 포맷 파서 — JSON / CSV → 정규화된 (식당, 리뷰) 목록 + 행별 오류.

최소 입력 스키마 (스펙 §1):
  restaurant: name(필수), category/address/lat/lng(선택)
  review: source(필수), text(필수), source_review_id/rating/reviewer_name/
          reviewer_review_count/reviewed_at/source_url(선택)

raw payload(원본 행)는 ParsedReview.raw에 그대로 보존한다.
"""
import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ParsedReview:
    restaurant_name: str
    category: str = ""
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    source: str = ""
    source_review_id: str | None = None
    rating: float | None = None
    text: str = ""
    reviewer_name: str | None = None
    reviewer_review_count: int | None = None
    reviewed_at: datetime | None = None
    source_url: str | None = None
    row: int = 0
    raw: dict = field(default_factory=dict)


@dataclass
class RowError:
    row: int
    field: str
    reason: str


_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                 "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S")


def _parse_date(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError):
            return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value) -> int | None:
    num = _num(value)
    return int(num) if num is not None else None


def _validate_review(data: dict, row: int, errors: list[RowError]) -> dict | None:
    """필수 필드 검증 — 실패 시 errors에 기록하고 None 반환."""
    text = str(data.get("text") or "").strip()
    source = str(data.get("source") or "").strip()
    restaurant_name = str(data.get("restaurant_name") or "").strip()

    if not restaurant_name:
        errors.append(RowError(row, "restaurant_name", "식당 이름이 비어 있습니다"))
        return None
    if not source:
        errors.append(RowError(row, "source", "리뷰 플랫폼(source)이 비어 있습니다"))
        return None
    if not text:
        errors.append(RowError(row, "text", "리뷰 본문이 비어 있습니다"))
        return None

    rating = _num(data.get("rating"))
    if rating is not None and not (1.0 <= rating <= 5.0):
        errors.append(RowError(row, "rating", f"별점 범위 초과 (1~5): {rating}"))
        return None
    return {
        "restaurant_name": restaurant_name,
        "category": str(data.get("category") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "lat": _num(data.get("lat")),
        "lng": _num(data.get("lng")),
        "source": source,
        "source_review_id": (str(data.get("source_review_id")).strip()
                             if data.get("source_review_id") not in (None, "") else None),
        "rating": rating,
        "text": text,
        "reviewer_name": (str(data.get("reviewer_name")).strip()
                          if data.get("reviewer_name") not in (None, "") else None),
        "reviewer_review_count": _int_or_none(data.get("reviewer_review_count")),
        "reviewed_at": _parse_date(data.get("reviewed_at")),
        "source_url": (str(data.get("source_url")).strip()
                       if data.get("source_url") not in (None, "") else None),
    }


def _to_parsed(clean: dict, row: int, raw: dict) -> ParsedReview:
    return ParsedReview(row=row, raw=raw, **clean)


def parse_json(content: str) -> tuple[list[ParsedReview], list[RowError]]:
    """지원 형태:
    1) {"restaurants": [{name..., "reviews": [{source, text, ...}]}]}
    2) {"reviews": [{restaurant_name|restaurant:{name,...}, source, text, ...}]}
    3) [ {식당+리뷰 플랫 형태}, ... ]
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return [], [RowError(0, "file", f"JSON 파싱 실패: {exc}")]

    if isinstance(data, dict) and "restaurants" in data:
        return _parse_nested(data["restaurants"])
    if isinstance(data, dict) and "reviews" in data:
        return _parse_flat_list(data["reviews"])
    if isinstance(data, list):
        return _parse_flat_list(data)
    return [], [RowError(0, "file", "루트가 restaurants/reviews 배열인 JSON이어야 합니다")]


def _parse_nested(restaurants: list) -> tuple[list[ParsedReview], list[RowError]]:
    parsed, errors = [], []
    row = 0
    for rest in restaurants:
        if not isinstance(rest, dict):
            errors.append(RowError(row, "restaurant", "식당 객체가 아닙니다"))
            continue
        base = {
            "category": str(rest.get("category") or "").strip(),
            "address": str(rest.get("address") or "").strip(),
            "lat": _num(rest.get("lat")),
            "lng": _num(rest.get("lng")),
            "restaurant_name": str(rest.get("name") or "").strip(),
        }
        reviews = rest.get("reviews") or []
        if not isinstance(reviews, list):
            errors.append(RowError(row, "reviews", "reviews 배열이 아닙니다"))
            continue
        for review in reviews:
            row += 1
            if not isinstance(review, dict):
                errors.append(RowError(row, "review", "리뷰 객체가 아닙니다"))
                continue
            merged = dict(base)
            merged.update({k: v for k, v in review.items()
                           if k not in ("restaurant_name", "name") and v not in (None, "")})
            clean = _validate_review(merged, row, errors)
            if clean:
                parsed.append(_to_parsed(clean, row, review))
    return parsed, errors


def _parse_flat_list(reviews: list) -> tuple[list[ParsedReview], list[RowError]]:
    parsed, errors = [], []
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, dict):
            errors.append(RowError(index, "review", "리뷰 객체가 아닙니다"))
            continue
        merged = dict(review)
        nested_restaurant = review.get("restaurant")
        if isinstance(nested_restaurant, dict):
            merged["restaurant_name"] = nested_restaurant.get("name")
            for key in ("category", "address", "lat", "lng"):
                if nested_restaurant.get(key) not in (None, ""):
                    merged.setdefault(key, nested_restaurant[key])
        clean = _validate_review(merged, index, errors)
        if clean:
            parsed.append(_to_parsed(clean, index, review))
    return parsed, errors


CSV_COLUMNS = ["restaurant_name", "category", "address", "lat", "lng", "source",
               "source_review_id", "rating", "text", "reviewer_name",
               "reviewer_review_count", "reviewed_at", "source_url"]


def parse_csv(content: str) -> tuple[list[ParsedReview], list[RowError]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or "restaurant_name" not in reader.fieldnames or "text" not in reader.fieldnames:
        return [], [RowError(0, "file",
                             f"CSV 헤더에 restaurant_name, text가 필요합니다 (권장: {','.join(CSV_COLUMNS)})")]
    parsed, errors = [], []
    for index, row in enumerate(reader, start=2):  # 헤더 다음 줄부터
        raw = dict(row)
        clean = _validate_review({k: v for k, v in row.items() if k in CSV_COLUMNS}, index, errors)
        if clean:
            parsed.append(_to_parsed(clean, index, raw))
    return parsed, errors


def parse_payload(format: str, content: str) -> tuple[list[ParsedReview], list[RowError]]:
    if format == "json":
        return parse_json(content)
    if format == "csv":
        return parse_csv(content)
    return [], [RowError(0, "format", f"지원하지 않는 형식: {format} (json|csv)")]
