"""Google Places Provider 테스트 — HTTP MockTransport로 API 응답 시뮬레이션 (스펙 §32)."""
import os
import tempfile
import unittest
from datetime import datetime

import httpx

from app.db.database import init_db, make_engine, make_session_factory
from app.db.mappers import restaurant_to_row
from app.db.models import RestaurantORM, ReviewORM
from app.models import Restaurant
from app.providers.base import ProviderRestaurant, ProviderReview
from app.providers.google_places import (
    GooglePlacesClient,
    GooglePlacesError,
    GooglePlacesProvider,
    haversine_m,
    match_restaurant,
    normalize_name,
    parse_google_place,
    parse_google_review,
)
from app.providers.google_places.import_service import (
    commit_google_import,
    preview_google_import,
)

# ── Google API 응답 fixture ──────────────────────────────────

SAMPLE_PLACE = {
    "id": "ChIJtest-place-001",
    "displayName": {"text": "성수동 돈까스", "languageCode": "ko"},
    "formattedAddress": "서울 성동구 성수동1가 1-1",
    "location": {"latitude": 37.5444, "longitude": 127.0557},
    "primaryType": "restaurant",
    "rating": 4.5,
    "userRatingCount": 1284,
    "googleMapsUri": "https://maps.google.com/?cid=12345",
}

SAMPLE_REVIEWS = [
    {
        "name": "places/ChIJtest/reviews/r1",
        "rating": 5,
        "text": {"text": "정말 맛있어요! 또 올게요", "languageCode": "ko"},
        "originalText": {"text": "정말 맛있어요! 또 올게요", "languageCode": "ko"},
        "authorAttribution": {"displayName": "김철수", "uri": "https://google.com/user/1"},
        "publishTime": "2026-07-15T10:30:00Z",
    },
    {
        "name": "places/ChIJtest/reviews/r2",
        "rating": 4,
        "text": {"text": "회사가 근처라 자주 갑니다. 이번이 세 번째.", "languageCode": "ko"},
        "authorAttribution": {"displayName": "이영희", "uri": "https://google.com/user/2"},
        "publishTime": "2026-08-01T12:00:00Z",
    },
]

SEARCH_RESPONSE = {"places": [SAMPLE_PLACE]}
DETAIL_RESPONSE = {**SAMPLE_PLACE, "reviews": SAMPLE_REVIEWS}


def make_provider(handler) -> GooglePlacesProvider:
    """MockTransport를 주입한 Provider."""
    client = GooglePlacesClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        retry_delays=(0, 0),
    )
    provider = GooglePlacesProvider.__new__(GooglePlacesProvider)
    provider._client = client
    return provider


class ParseTest(unittest.TestCase):
    def test_parse_place(self):
        place = parse_google_place(SAMPLE_PLACE)
        self.assertEqual(place.provider, "google_places")
        self.assertEqual(place.provider_place_id, "ChIJtest-place-001")
        self.assertEqual(place.name, "성수동 돈까스")
        self.assertEqual(place.rating, 4.5)
        self.assertEqual(place.user_rating_count, 1284)
        self.assertIn("primary_type", place.provider_metadata)

    def test_parse_review(self):
        review = parse_google_review(SAMPLE_REVIEWS[0], "ChIJtest-place-001")
        self.assertEqual(review.provider, "google_places")
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.author_name, "김철수")
        self.assertTrue(review.provider_metadata["source_sample_limited"])
        self.assertEqual(review.provider_metadata["content_owner"], "google")
        self.assertIsNotNone(review.published_at)

    def test_haversine(self):
        # 성수동 좌표 근처 — 약 50m
        d = haversine_m(37.5444, 127.0557, 37.5448, 127.0557)
        self.assertAlmostEqual(d, 44, delta=5)
        # 같은 좌표
        self.assertEqual(haversine_m(37.5, 127.0, 37.5, 127.0), 0)

    def test_normalize_name(self):
        self.assertEqual(normalize_name("성수동 돈까스"), "성수동돈까스")
        self.assertEqual(normalize_name("  성수동돈까스  "), "성수동돈까스")


class MatchTest(unittest.TestCase):
    def _make_restaurant(self, id, name, lat=0, lng=0, address="", raw=None):
        r = RestaurantORM(id=id, name=name, lat=lat, lng=lng, address=address)
        if raw:
            r.raw_payload = raw
        return r

    def test_exact_place_id_match(self):
        place = parse_google_place(SAMPLE_PLACE)
        existing = [self._make_restaurant("r1", "다른이름", raw={
            "source_refs": {"google_place_id": "ChIJtest-place-001"}
        })]
        result = match_restaurant(place, existing)
        self.assertEqual(result.match_type, "exact_place_id")
        self.assertEqual(result.matched_restaurant_id, "r1")
        self.assertEqual(result.confidence, 1.0)

    def test_name_coords_match(self):
        place = parse_google_place(SAMPLE_PLACE)  # lat=37.5444
        existing = [self._make_restaurant("r1", "성수동 돈까스", lat=37.5444, lng=127.0557)]
        result = match_restaurant(place, existing)
        self.assertEqual(result.match_type, "name_coords")
        self.assertEqual(result.matched_restaurant_id, "r1")
        self.assertLess(result.distance_m, 5)

    def test_name_address_match(self):
        place = parse_google_place(SAMPLE_PLACE)
        existing = [self._make_restaurant("r1", "성수동 돈까스", address="서울 성동구 성수동1가 1-1")]
        result = match_restaurant(place, existing)
        self.assertEqual(result.match_type, "name_address")

    def test_no_match_same_name_far_coords(self):
        """이름이 같아도 좌표가 멀면 자동 merge 금지 (스펙 §5)."""
        place = parse_google_place(SAMPLE_PLACE)  # 성수동
        existing = [self._make_restaurant("r1", "성수동 돈까스", lat=37.5, lng=126.9)]  # 다른 위치
        result = match_restaurant(place, existing)
        self.assertEqual(result.match_type, "no_match")
        self.assertEqual(result.confidence, 0.0)

    def test_no_match_completely_different(self):
        place = parse_google_place(SAMPLE_PLACE)
        existing = [self._make_restaurant("r1", "을지면옥")]
        result = match_restaurant(place, existing)
        self.assertEqual(result.match_type, "no_match")


class ClientTest(unittest.TestCase):
    def test_search_success(self):
        def handler(request):
            return httpx.Response(200, json=SEARCH_RESPONSE)

        provider = make_provider(handler)
        results = provider.search_places("성수동 돈까스")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "성수동 돈까스")
        provider.close()

    def test_get_place_with_reviews(self):
        def handler(request):
            return httpx.Response(200, json=DETAIL_RESPONSE)

        provider = make_provider(handler)
        place = provider.get_place("ChIJtest-place-001")
        reviews = provider.get_reviews("ChIJtest-place-001")
        self.assertIsNotNone(place)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].rating, 5)
        provider.close()

    def test_404_place_not_found(self):
        def handler(request):
            return httpx.Response(404, json={"error": {"message": "not found"}})

        provider = make_provider(handler)
        self.assertIsNone(provider.get_place("nonexistent"))
        provider.close()

    def test_403_auth_error(self):
        def handler(request):
            return httpx.Response(403, json={"error": {"message": "forbidden"}})

        provider = make_provider(handler)
        with self.assertRaises(GooglePlacesError) as ctx:
            provider.search_places("test")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertFalse(ctx.exception.retryable)
        provider.close()

    def test_429_retry_then_success(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) <= 2:
                return httpx.Response(429, json={"error": {"message": "rate limit"}})
            return httpx.Response(200, json=SEARCH_RESPONSE)

        provider = make_provider(handler)
        results = provider.search_places("test")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(calls), 3)  # 1 + 2 retry
        provider.close()

    def test_no_api_key(self):
        with self.assertRaises(GooglePlacesError):
            GooglePlacesClient(api_key="")


class ImportServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import pathlib
        url = "sqlite:///" + str(pathlib.Path(self.tmp.name) / "gp.db").replace("\\", "/")
        self.engine = make_engine(url)
        init_db(self.engine)
        self.sf = make_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _place(self):
        return parse_google_place(SAMPLE_PLACE)

    def _reviews(self):
        return [parse_google_review(r, "ChIJtest-place-001") for r in SAMPLE_REVIEWS]

    def test_preview_no_existing(self):
        with self.sf() as session:
            preview = preview_google_import(session, self._place(), self._reviews())
        self.assertEqual(preview.match.match_type, "no_match")
        self.assertEqual(preview.new_reviews, 2)
        self.assertEqual(preview.duplicates, 0)
        self.assertEqual(preview.existing_reviews, 0)

    def test_commit_creates_restaurant_and_reviews(self):
        with self.sf() as session:
            result = commit_google_import(session, self._place(), self._reviews())
            self.assertEqual(result.action, "created")
            self.assertEqual(result.inserted_reviews, 2)

            # 검증
            restaurant = session.query(RestaurantORM).first()
            self.assertIsNotNone(restaurant)
            self.assertEqual(restaurant.name, "성수동 돈까스")
            raw = restaurant.provider_metadata
            self.assertEqual(raw["source_refs"]["google_place_id"], "ChIJtest-place-001")
            self.assertEqual(raw["google_rating"], 4.5)

            reviews = session.query(ReviewORM).all()
            self.assertEqual(len(reviews), 2)
            self.assertEqual(reviews[0].source, "google_places")
            self.assertTrue(reviews[0].raw_payload["source_sample_limited"])
            self.assertIn("attribution", reviews[0].raw_payload["provider_metadata"])

    def test_reimport_all_duplicates(self):
        with self.sf() as session:
            commit_google_import(session, self._place(), self._reviews())
            # 재 Import → 전부 중복
            result2 = commit_google_import(session, self._place(), self._reviews())
            self.assertEqual(result2.action, "linked")  # 이미 존재
            self.assertEqual(result2.inserted_reviews, 0)
            self.assertEqual(result2.skipped_duplicates, 2)

    def test_place_id_duplicate_prevention(self):
        """동일 google place를 중복 Import해도 식당이 하나만 생성된다 (스펙 §16)."""
        with self.sf() as session:
            commit_google_import(session, self._place(), self._reviews())
            count = session.query(RestaurantORM).count()
            self.assertEqual(count, 1)

    def test_match_existing_and_link(self):
        """기존 식당(좌표 일치)을 찾아 연결 (스펙 §15)."""
        with self.sf() as session:
            # 기존 식당 생성 (같은 이름 + 근처 좌표)
            session.add(RestaurantORM(
                id="manual-r1", name="성수동 돈까스",
                lat=37.5444, lng=127.0557, address="",
            ))
            session.commit()

            preview = preview_google_import(session, self._place(), self._reviews())
            self.assertEqual(preview.match.match_type, "name_coords")
            self.assertEqual(preview.match.matched_restaurant_id, "manual-r1")

            result = commit_google_import(session, self._place(), self._reviews())
            self.assertEqual(result.action, "linked")
            self.assertEqual(result.restaurant_id, "manual-r1")

            # google_place_id가 기존 식당에 기록됨
            linked = session.get(RestaurantORM, "manual-r1")
            self.assertEqual(
                linked.provider_metadata["source_refs"]["google_place_id"],
                "ChIJtest-place-001")

    def test_force_new_overrides_match(self):
        """force_new=True면 매칭을 무시하고 신규 생성 (수동 override)."""
        with self.sf() as session:
            session.add(RestaurantORM(
                id="manual-r1", name="성수동 돈까스",
                lat=37.5444, lng=127.0557,
            ))
            session.commit()

            result = commit_google_import(
                session, self._place(), self._reviews(), force_new=True)
            self.assertEqual(result.action, "created")
            self.assertNotEqual(result.restaurant_id, "manual-r1")

    def test_empty_reviews(self):
        """리뷰가 0개여도 식당은 생성된다 (스펙 §32)."""
        with self.sf() as session:
            result = commit_google_import(session, self._place(), [])
            self.assertEqual(result.action, "created")
            self.assertEqual(result.inserted_reviews, 0)
            self.assertEqual(result.review_samples_total, 0)

    def test_blank_reviews_skipped(self):
        """빈 텍스트 리뷰는 건너뛴다."""
        blank_review = ProviderReview(
            provider="google_places", text="   ", rating=3.0,
        )
        with self.sf() as session:
            result = commit_google_import(
                session, self._place(), [blank_review] + self._reviews())
            self.assertEqual(result.inserted_reviews, 2)  # blank 제외
            self.assertEqual(result.review_samples_total, 2)


class HaversineTest(unittest.TestCase):
    def test_known_distances(self):
        # 서울역 → 강남역 약 10km
        d = haversine_m(37.5563, 126.9723, 37.4979, 127.0276)
        self.assertAlmostEqual(d / 1000, 8.1, delta=1.5)

    def test_zero_distance(self):
        self.assertEqual(haversine_m(37.5, 127.0, 37.5, 127.0), 0.0)

    def test_same_lat_small_lng_change(self):
        # 경도 0.001도 ≈ 90m (서울 위도 기준)
        d = haversine_m(37.5, 127.0, 37.5, 127.001)
        self.assertAlmostEqual(d, 89, delta=5)


if __name__ == "__main__":
    unittest.main()
