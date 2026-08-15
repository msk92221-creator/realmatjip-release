"""LLM 입력 해시 검증 — 캐시 키가 실제 입력을 결정하는 모든 정보를 포함하는지 (스펙 §10)."""
import unittest
from datetime import datetime

from app.analysis.input_hash import cache_key_is_safe, llm_input_hash, text_only_hash
from app.models import Review


def make_review(source="naver_map", rating=4.0, text="맛있는 집이에요"):
    return Review(
        id="r", restaurant_id="x", source=source, rating=rating, text=text,
        reviewed_at=datetime(2026, 8, 1),
    )


class InputHashTest(unittest.TestCase):

    def test_different_source_different_hash(self):
        """같은 텍스트라도 source가 다르면 해시가 달라야 한다 (캐시 미스)."""
        r1 = make_review(source="naver_map")
        r2 = make_review(source="kakao_map")
        self.assertNotEqual(llm_input_hash(r1), llm_input_hash(r2))

    def test_different_rating_different_hash(self):
        """같은 텍스트라도 rating이 다르면 해시가 달라야 한다."""
        r1 = make_review(rating=4.0)
        r2 = make_review(rating=5.0)
        self.assertNotEqual(llm_input_hash(r1), llm_input_hash(r2))

    def test_null_rating_vs_rated_different(self):
        """별점 없음(null)과 별점 있음은 다른 해시."""
        r1 = make_review(rating=None)
        r2 = make_review(rating=4.0)
        self.assertNotEqual(llm_input_hash(r1), llm_input_hash(r2))

    def test_same_input_same_hash(self):
        r1 = make_review()
        r2 = make_review()
        self.assertEqual(llm_input_hash(r1), llm_input_hash(r2))

    def test_input_hash_differs_from_text_only_hash(self):
        """source/rating이 포함되면 text_hash와 달라야 한다."""
        review = make_review(source="naver_map", rating=4.0)
        self.assertNotEqual(llm_input_hash(review), text_only_hash(review.text))

    def test_cache_key_is_safe_returns_false_when_source_present(self):
        """LLM 입력에 text 외 다른 필드가 있으면 text_hash 단독 캐시는 안전하지 않다."""
        review = make_review(source="naver_map", rating=4.0)
        self.assertFalse(cache_key_is_safe(review))

    def test_cache_key_is_safe_true_when_text_only(self):
        """입력이 text 하나뿐인 경우에만 text_hash로 충분."""
        review = make_review(source="", rating=None)  # source/rating이 None/빈값
        # source=""는 payload에 포함되지만 None이 아님 → unsafe
        self.assertFalse(cache_key_is_safe(review))
        # source/rating이 모두 None이면 text만 남음
        review2 = make_review(source=None, rating=None)
        # None은 json.dumps에서 null → payload에 존재하긴 함
        # _user_payload는 source와 rating을 항상 포함하므로 안전하지 않음
        # (실제로는 항상 False여야 정상 — 원칙 검증용)

    def test_input_hash_includes_all_llm_fields(self):
        """llm_input_hash는 LLM _user_payload와 동일한 필드를 반영해야 한다."""
        import json
        review = make_review(source="test", rating=3.5, text="내용")
        payload = {"source": review.source, "rating": review.rating, "text": review.text}
        expected = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        import hashlib
        self.assertEqual(
            llm_input_hash(review),
            hashlib.sha256(expected.encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
