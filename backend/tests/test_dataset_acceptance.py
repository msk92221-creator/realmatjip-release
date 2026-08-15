"""Synthetic dataset + 종단(end-to-end) 인수 테스트 — 스펙 §39 합격 기준."""
import unittest

from app.config import ScoringConfig
from app.scoring.engine import naive_ranking, rank_by, score_dataset

from fixtures.dataset import EXPECTED_COUNTS, REFERENCE_DATE, build_dataset

CFG = ScoringConfig()


class DatasetFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.restaurants, cls.reviews = build_dataset()
        cls.results = score_dataset(cls.restaurants, cls.reviews, CFG, REFERENCE_DATE)
        cls.by_id = {r.restaurant.id: r for r in cls.results}

    def test_counts(self):
        self.assertEqual(len(self.reviews), 175)
        for rid, expected in EXPECTED_COUNTS.items():
            actual = sum(1 for r in self.reviews if r.restaurant_id == rid)
            self.assertEqual(actual, expected, rid)

    def test_all_reviews_analyzed_with_rating(self):
        for review in self.reviews:
            self.assertIsNotNone(review.analysis, review.id)
            self.assertIsNotNone(review.rating, review.id)

    def test_deterministic(self):
        restaurants2, reviews2 = build_dataset()
        results2 = score_dataset(restaurants2, reviews2, CFG, REFERENCE_DATE)
        for r1, r2 in zip(self.results, results2):
            self.assertAlmostEqual(r1.overall_a.score, r2.overall_a.score)


class RankingInvariantTest(unittest.TestCase):
    """결정 #2: 고정 기대 순위가 아니라 핵심 invariant를 검증한다."""

    @classmethod
    def setUpClass(cls):
        cls.restaurants, cls.reviews = build_dataset()
        cls.results = score_dataset(cls.restaurants, cls.reviews, CFG, REFERENCE_DATE)
        cls.by_id = {r.restaurant.id: r for r in cls.results}
        cls.ranked = rank_by(cls.results, "A")
        cls.rank_of = {r.restaurant.id: i for i, r in enumerate(cls.ranked)}
        cls.naive = naive_ranking(cls.restaurants, cls.reviews)
        cls.naive_mean = {rest.id: mean for rest, mean, _ in cls.naive}

    def test_scores_valid(self):
        for result in self.results:
            self.assertIsNotNone(result.overall_a.score, result.restaurant.id)
            self.assertTrue(0 <= result.overall_a.score <= 100)
            self.assertIsNotNone(result.overall_b.score)

    def test_naive_star_ranking_is_deceived_by_ads(self):
        """단순 별점 평균은 광고 리뷰에 속아 A를 1위로 올린다."""
        self.assertEqual(self.naive[0][0].id, "rest-a")

    def test_invariant_a_drops_sharply(self):
        """A는 단순 별점 대비 순위와 평점 모두 크게 하락해야 한다."""
        self.assertGreaterEqual(self.rank_of["rest-a"], 3)  # 최소 2계단 하락
        a = self.by_id["rest-a"]
        drop = a.sub.rating_adjusted - self.naive_mean["rest-a"]
        self.assertLessEqual(drop, -0.03)  # r01 기준 −0.03 이상 하락

    def test_invariant_b_and_d_top_tier(self):
        top2 = {r.restaurant.id for r in self.ranked[:2]}
        self.assertEqual(top2, {"rest-b", "rest-d"})

    def test_invariant_e_below_b_and_d(self):
        self.assertGreater(self.rank_of["rest-e"], self.rank_of["rest-b"])
        self.assertGreater(self.rank_of["rest-e"], self.rank_of["rest-d"])

    def test_invariant_c_manipulation_high_vs_genuine(self):
        c = self.by_id["rest-c"].manipulation.score
        for rid in ("rest-b", "rest-d", "rest-e"):
            self.assertGreater(c, self.by_id[rid].manipulation.score, rid)

    def test_invariant_c_not_overpunished_for_virality(self):
        """바이럴 자체는 광고가 아니므로 C의 보정 평점은 크게 깎이지 않는다."""
        c = self.by_id["rest-c"]
        drop = c.sub.rating_adjusted - self.naive_mean["rest-c"]
        self.assertGreaterEqual(drop, -0.15)

    def test_b_beats_a_by_wide_margin(self):
        gap = self.by_id["rest-b"].overall_a.score - self.by_id["rest-a"].overall_a.score
        self.assertGreater(gap, 15.0)

    def test_ad_weighting_lowers_a_rating(self):
        a = self.by_id["rest-a"]
        self.assertLess(a.sub.rating_adjusted, self.naive_mean["rest-a"] - 0.03)

    def test_genuine_restaurant_rating_not_punished(self):
        """광고 없는 식당(B)의 보정 평점은 단순 평균에서 크게 벗어나지 않는다."""
        b = self.by_id["rest-b"]
        self.assertGreater(b.sub.rating_adjusted, self.naive_mean["rest-b"] - 0.03)

    def test_evidence_strength_ordering(self):
        """근거 강도(결정 #1): B의 유효 근거가 D보다 많아야 한다."""
        self.assertGreater(self.by_id["rest-b"].sub.evidence_strength,
                           self.by_id["rest-d"].sub.evidence_strength)


class SignalAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.restaurants, cls.reviews = build_dataset()
        cls.results = score_dataset(cls.restaurants, cls.reviews, CFG, REFERENCE_DATE)
        cls.by_id = {r.restaurant.id: r for r in cls.results}

    def test_a_manipulation_risk_above_b(self):
        self.assertGreater(
            self.by_id["rest-a"].manipulation.score,
            self.by_id["rest-b"].manipulation.score,
        )

    def test_c_duplicate_cluster_detected(self):
        self.assertGreaterEqual(self.by_id["rest-c"].dup_count, 8)

    def test_d_genuine_reviews_not_flagged_duplicate(self):
        self.assertEqual(self.by_id["rest-d"].dup_count, 0)

    def test_e_consistency_below_b(self):
        self.assertLess(self.by_id["rest-e"].consistency, self.by_id["rest-b"].consistency)

    def test_local_badges(self):
        self.assertTrue(self.by_id["rest-b"].local_badge)
        self.assertTrue(self.by_id["rest-d"].local_badge)
        self.assertFalse(self.by_id["rest-c"].local_badge)
        self.assertFalse(self.by_id["rest-a"].local_badge)

    def test_c_has_lowest_local_score(self):
        self.assertLess(self.by_id["rest-c"].sub.local, self.by_id["rest-b"].sub.local)

    def test_old_nopo_gets_longevity_reward(self):
        self.assertGreater(self.by_id["rest-d"].longevity, self.by_id["rest-b"].longevity)


if __name__ == "__main__":
    unittest.main()
