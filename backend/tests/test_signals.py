import unittest

from app.config import ScoringConfig
from app.scoring.signals import consistency, longevity, manipulation, platform_stats

from .helpers import REFERENCE, make_review

CFG = ScoringConfig()


def with_weights(reviews, weight=0.8):
    return {r.id: weight for r in reviews}


class TestConsistency(unittest.TestCase):
    def _stats(self, per_platform: dict[str, list[float]], weight: float = 0.8):
        reviews = []
        for source, ratings in per_platform.items():
            for i, rating in enumerate(ratings):
                reviews.append(make_review(f"{source}-{i}", source=source, rating=rating))
        weights = with_weights(reviews, weight)
        return platform_stats(reviews, weights, set(), dataset_prior=0.85, cfg=CFG)

    def test_agreeing_platforms_score_high(self):
        stats = self._stats({"google_places": [4.8, 4.7, 4.8], "naver_map": [4.7, 4.8, 4.7]})
        self.assertGreater(consistency(stats, CFG), 0.75)

    def test_diverging_platforms_score_low(self):
        stats = self._stats({"google_places": [4.9, 4.8, 4.9], "naver_map": [3.2, 3.0, 3.4]})
        self.assertLess(consistency(stats, CFG), 0.5)

    def test_single_platform_is_neutral_low(self):
        stats = self._stats({"google_places": [4.8, 4.7, 4.8]})
        self.assertAlmostEqual(consistency(stats, CFG), CFG.consistency_single_platform)

    def test_three_platforms_beat_two_at_same_sd(self):
        two = self._stats({"google_places": [4.8] * 3, "naver_map": [4.6] * 3})
        three = self._stats({
            "google_places": [4.8] * 3, "naver_map": [4.7] * 3, "kakao_map": [4.6] * 3,
        })
        # 두 경우 모두 일관적이지만 2플랫폼은 검증 부족 팩터가 적용된다
        self.assertGreater(consistency(three, CFG), consistency(two, CFG) * 0.9)


class TestPlatformGate(unittest.TestCase):
    """결정 #5: unique 리뷰 수와 유효 가중치 이중 게이트."""

    def _reviews(self, source: str, ratings: list[float]):
        return [make_review(f"g-{source}-{i}", source=source, rating=r)
                for i, r in enumerate(ratings)]

    def test_low_weight_platform_excluded(self):
        # 리뷰 수는 충분(3개)해도 유효 가중치 합 0.9 < 1.5 → 게이트 탈락
        reviews = self._reviews("google_places", [4.8, 4.7, 4.8])
        stats = platform_stats(reviews, with_weights(reviews, 0.3), set(), 0.85, CFG)
        self.assertEqual(stats, [])
        self.assertAlmostEqual(consistency(stats, CFG), CFG.consistency_single_platform)

    def test_high_weight_platform_passes(self):
        reviews = self._reviews("naver_map", [4.8, 4.7, 4.8])
        stats = platform_stats(reviews, with_weights(reviews, 0.8), set(), 0.85, CFG)
        self.assertEqual(len(stats), 1)

    def test_duplicate_reviews_excluded_from_gate(self):
        # 4개 리뷰 중 3개가 중복 멤버면 unique 1개 → 게이트 탈락
        reviews = self._reviews("kakao_map", [4.8, 4.8, 4.7, 4.9])
        dup_ids = {r.id for r in reviews[1:]}
        stats = platform_stats(reviews, with_weights(reviews, 0.8), dup_ids, 0.85, CFG)
        self.assertEqual(stats, [])


class TestManipulation(unittest.TestCase):
    def test_burst_detected(self):
        reviews = (
            [make_review(f"m-{i}", days=100 + i) for i in range(3)]      # 5월: 3개
            + [make_review(f"j-{i}", days=66 + i) for i in range(3)]     # 6월: 3개
            + [make_review(f"jl-{i}", days=33 + i) for i in range(3)]    # 7월: 3개
            + [make_review(f"p-{i}", days=1 + i % 5) for i in range(30)] # 8월: 30개 폭발
        )
        detail = manipulation(reviews, set(), CFG)
        self.assertGreater(detail.burst01, 0.5)
        self.assertGreater(detail.score, 0.3)

    def test_steady_stream_no_burst(self):
        reviews = (
            [make_review(f"m-{i}", days=100 + i) for i in range(3)]
            + [make_review(f"j-{i}", days=66 + i) for i in range(4)]
            + [make_review(f"jl-{i}", days=32 + i) for i in range(3)]
        )
        detail = manipulation(reviews, set(), CFG)
        self.assertAlmostEqual(detail.burst01, 0.0)
        self.assertAlmostEqual(detail.score, 0.0)

    def test_new_restaurant_single_month_not_flagged(self):
        """한 달밖에 안 된 새 식당의 리뷰 집중은 폭발로 보지 않는다."""
        reviews = [make_review(f"n-{i}", days=1 + i) for i in range(5)]
        detail = manipulation(reviews, set(), CFG)
        self.assertAlmostEqual(detail.burst01, 0.0)

    def test_dup_share_contributes(self):
        reviews = [make_review(f"d-{i}") for i in range(10)]
        detail = manipulation(reviews, {f"d-{i}" for i in range(4)}, CFG)
        self.assertAlmostEqual(detail.dup01, 0.4)
        self.assertGreater(detail.score, CFG.manip_dup_share * 0.4 - 1e-9)


class TestLongevity(unittest.TestCase):
    def test_long_steady_nopo_rewards(self):
        reviews = [
            make_review("y1", days=1100, rating=4.5),
            make_review("y2", days=730, rating=4.6),
            make_review("y3", days=365, rating=4.5),
            make_review("y4", days=10, rating=4.6),
        ]
        result = longevity(reviews, with_weights(reviews), CFG, REFERENCE)
        self.assertGreater(result, 0.5)

    def test_short_history_low(self):
        reviews = [make_review("s1", days=20, rating=4.8), make_review("s2", days=5, rating=4.9)]
        result = longevity(reviews, with_weights(reviews), CFG, REFERENCE)
        self.assertLess(result, 0.1)

    def test_unstable_years_not_rewarded(self):
        reviews = [
            make_review("u1", days=1100, rating=5.0),
            make_review("u2", days=730, rating=2.0),
            make_review("u3", days=365, rating=5.0),
            make_review("u4", days=10, rating=2.0),
        ]
        result = longevity(reviews, with_weights(reviews), CFG, REFERENCE)
        self.assertLess(result, 0.2)

    def test_weak_evidence_half_stability(self):
        reviews = [make_review("w1", days=100, rating=4.5), make_review("w2", days=80, rating=4.6)]
        result = longevity(reviews, with_weights(reviews, weight=0.2), CFG, REFERENCE)
        # 단일 연도, 저근거 → span 작고 안정성 절반
        self.assertLessEqual(result, 0.1)


if __name__ == "__main__":
    unittest.main()
