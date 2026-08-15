import unittest

from app.config import ScoringConfig
from app.scoring.weights import (
    ReviewWeight,
    effective_ad_probability,
    review_weight,
    reviewer_factor,
)

from .helpers import REFERENCE, make_analysis, make_review

CFG = ScoringConfig()


def weight_of(ad: float = 0.1, conf: float = 0.9, days: int = 10,
              auth: float = 0.85, spec: float = 0.85,
              source: str = "google_places", rcount: int | None = 50) -> float:
    review = make_review(
        "w", source=source, days=days, rcount=rcount,
        analysis=make_analysis(ad=ad, conf=conf, auth=auth, spec=spec),
    )
    return review_weight(review, CFG, REFERENCE).weight


class TestAdWeightCurve(unittest.TestCase):
    def test_weight_decreases_monotonically_with_ad_probability(self):
        weights = [weight_of(ad=p, conf=1.0) for p in (0.0, 0.2, 0.5, 0.8, 1.0)]
        for earlier, later in zip(weights, weights[1:]):
            self.assertGreaterEqual(earlier, later)
        self.assertGreater(weights[0] - weights[-1], 0.5)

    def test_p1_hits_floor(self):
        self.assertAlmostEqual(weight_of(ad=1.0, conf=1.0), CFG.w_min)

    def test_design_table_reproduction(self):
        """스펙 §8 표: p=0.8 → w≈0.09 (다른 인자가 1일 때), p=0 → w≈0.93."""
        review = make_review(
            "p08", source="google_places", days=1, rcount=100,
            analysis=make_analysis(ad=0.8, conf=1.0, auth=1.0, spec=1.0),
        )
        w = review_weight(review, CFG, REFERENCE).weight
        self.assertLess(w, 0.16)
        self.assertGreater(w, 0.05)

        clean = make_review(
            "p00", source="google_places", days=1, rcount=100,
            analysis=make_analysis(ad=0.0, conf=1.0, auth=1.0, spec=1.0),
        )
        self.assertGreater(review_weight(clean, CFG, REFERENCE).weight, 0.85)

    def test_qual_floor_protects_short_genuine_review(self):
        """진솔하지만 정보량 없는 짧은 리뷰는 과살상하지 않는다."""
        w = weight_of(ad=0.1, conf=0.9, auth=0.9, spec=0.0)
        self.assertGreater(w, 0.3)

    def test_duplicate_member_reduced(self):
        review = make_review("d")
        normal = review_weight(review, CFG, REFERENCE, duplicate=False).weight
        dup = review_weight(review, CFG, REFERENCE, duplicate=True).weight
        self.assertAlmostEqual(dup, normal * CFG.dup_member_factor)


class TestEffectiveAdProbability(unittest.TestCase):
    def test_manual_label_overrides_llm(self):
        # LLM은 광고로 봤지만 수동 라벨이 'normal' → p_eff 낮음 (사람이 LLM보다 우선)
        p = effective_ad_probability(make_analysis(ad=0.95), "normal", CFG)
        self.assertAlmostEqual(p, 0.05)
        p = effective_ad_probability(make_analysis(ad=0.0), "ad", CFG)
        self.assertAlmostEqual(p, 0.95)

    def test_unknown_label_raises(self):
        with self.assertRaises(ValueError):
            effective_ad_probability(make_analysis(), "sure", CFG)

    def test_zero_confidence_shrinks_to_prior(self):
        p = effective_ad_probability(make_analysis(ad=0.9, conf=0.0), None, CFG)
        self.assertAlmostEqual(p, CFG.ad_prior)

    def test_confidence_mixture(self):
        p = effective_ad_probability(make_analysis(ad=0.9, conf=0.5), None, CFG)
        self.assertAlmostEqual(p, 0.5 * 0.9 + 0.5 * CFG.ad_prior)

    def test_prior_is_configurable(self):
        """D5: ad_prior는 설정값이며 관측값으로 교체 가능하다."""
        cfg = ScoringConfig(ad_prior=0.55)
        p = effective_ad_probability(make_analysis(ad=0.9, conf=0.0), None, cfg)
        self.assertAlmostEqual(p, 0.55)


class TestRecency(unittest.TestCase):
    def test_tier_values(self):
        cases = [(1, 1.00), (4, 0.90), (7, 0.80), (13, 0.65), (30, 0.45)]
        for months, expected in cases:
            self.assertAlmostEqual(CFG.recency_factor(months), expected, msg=f"{months}개월")

    def test_old_review_weighted_less(self):
        fresh = weight_of(days=5)
        old = weight_of(days=800)
        self.assertLess(old, fresh * 0.6)


class TestReviewerFactor(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(reviewer_factor(make_review("a", rcount=50), CFG), 1.0)
        self.assertEqual(reviewer_factor(make_review("b", rcount=10), CFG), 0.8)
        self.assertEqual(reviewer_factor(make_review("c", rcount=3), CFG), 0.6)
        self.assertEqual(reviewer_factor(make_review("d", rcount=None), CFG), 0.85)

    def test_source_weight_applied(self):
        blog = weight_of(source="naver_blog")
        google = weight_of(source="google_places")
        self.assertLess(blog, google)


class TestReviewWeightResult(unittest.TestCase):
    def test_factors_exposed_for_debugging(self):
        rw: ReviewWeight = review_weight(make_review("f"), CFG, REFERENCE)
        for key in ("p_eff", "f_ad", "f_qual", "f_src", "f_rev", "f_time"):
            self.assertIn(key, rw.factors)
        self.assertTrue(0.0 <= rw.weight <= 1.0)


if __name__ == "__main__":
    unittest.main()
