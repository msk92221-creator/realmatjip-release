import unittest

from app.config import ScoringConfig
from app.scoring.scores import (
    ManipulationDetail,
    SubScores,
    overall,
    sub_scores,
    trust_value,
)

CFG = ScoringConfig()


def make_sub(n_eff: float = 20.0, rating: float = 0.9, **overrides) -> SubScores:
    defaults = dict(
        n_eff=n_eff,
        evidence_strength=n_eff / (n_eff + CFG.evidence_c),
        rating_adjusted=rating, ad_free=0.8, trust=0.8, local=0.55, repeat=0.2,
        food=0.75, value=0.7, n_raw=30, local_evidence=5.0,
        dataset_prior=0.85, mean_p_eff=0.1, ad_share_07=0.05,
    )
    defaults.update(overrides)
    return SubScores(**defaults)


NO_MANIP = ManipulationDetail(score=0.0, burst01=0.0, dup01=0.0,
                              peak_month_count=0, median_month_count=0.0, active_months=0)


class TestTrustValue(unittest.TestCase):
    def test_formula(self):
        expected = (CFG.trust_ad_share * 0.8 + CFG.trust_auth_share * 0.8 + CFG.trust_spec_share * 0.6)
        self.assertAlmostEqual(trust_value(0.2, 0.8, 0.6, CFG), expected)

    def test_shares_are_configurable(self):
        cfg = ScoringConfig(trust_ad_share=1.0, trust_auth_share=0.0, trust_spec_share=0.0)
        self.assertAlmostEqual(trust_value(0.3, 0.9, 0.9, cfg), 0.7)

    def test_genuine_low_ad_high_trust(self):
        self.assertGreater(
            trust_value(0.05, 0.9, 0.9, CFG), trust_value(0.85, 0.2, 0.5, CFG)
        )


class TestEvidenceStrength(unittest.TestCase):
    """결정 #1: Overall에 반영하지 않는, 표시 전용 근거 강도."""

    def test_formula_and_bounds(self):
        sub = sub_scores(
            r01s=[0.9], rated_weights=[20.0],
            p_effs=[0.1], trust_values=[0.9], local_probs=[0.5], repeat_flags=[0.0],
            all_weights=[20.0], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=25, local_evidence=0.0,
        )
        self.assertAlmostEqual(sub.evidence_strength, 20.0 / 28.0, places=3)
        self.assertLessEqual(sub.evidence_strength, 1.0)

    def test_zero_evidence(self):
        sub = sub_scores(
            r01s=[], rated_weights=[],
            p_effs=[], trust_values=[], local_probs=[], repeat_flags=[],
            all_weights=[], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=0, local_evidence=0.0,
        )
        self.assertAlmostEqual(sub.evidence_strength, 0.0)


class TestOverallGate(unittest.TestCase):
    def test_insufficient_data_returns_none(self):
        """리뷰 2개/평점 5.0이라는 이유로 상위에 오르는 것을 차단."""
        result = overall(make_sub(n_eff=1.5, rating=1.0), 1.0, 1.0, NO_MANIP, CFG, "A")
        self.assertIsNone(result.score)

    def test_sufficient_data_returns_score(self):
        result = overall(make_sub(n_eff=5.0), 0.8, 0.5, NO_MANIP, CFG, "A")
        self.assertIsNotNone(result.score)


class TestOverallComputation(unittest.TestCase):
    def test_perfect_inputs_reach_100(self):
        result = overall(make_sub(n_eff=30, rating=1.0, trust=1.0, local=1.0, repeat=1.0),
                         1.0, 1.0, NO_MANIP, CFG, "A")
        self.assertAlmostEqual(result.score, 100.0)

    def test_score_equals_term_sum(self):
        result = overall(make_sub(), 0.9, 0.4, NO_MANIP, CFG, "A")
        term_sum = sum(points for _, _, points in result.terms)
        self.assertAlmostEqual(result.score, term_sum)

    def test_manipulation_penalty_capped(self):
        worst = ManipulationDetail(score=1.0, burst01=1.0, dup01=1.0,
                                   peak_month_count=99, median_month_count=1.0, active_months=6)
        clean = overall(make_sub(), 0.8, 0.5, NO_MANIP, CFG, "A").score
        dirty = overall(make_sub(), 0.8, 0.5, worst, CFG, "A").score
        self.assertAlmostEqual(clean - dirty, CFG.manipulation_penalty_max)

    def test_version_b_lower_rating_weight_changes_score(self):
        a = overall(make_sub(), 0.9, 0.5, NO_MANIP, CFG, "A")
        b = overall(make_sub(), 0.9, 0.5, NO_MANIP, CFG, "B")
        self.assertNotAlmostEqual(a.score, b.score)

    def test_clamped_to_zero(self):
        terrible = make_sub(n_eff=5.0, rating=0.0, trust=0.0, local=0.0, repeat=0.0)
        result = overall(terrible, 0.0, 0.0,
                         ManipulationDetail(1.0, 1.0, 1.0, 99, 1.0, 6), CFG, "A")
        self.assertGreaterEqual(result.score, 0.0)


class TestSubScores(unittest.TestCase):
    def test_rating_shrinks_toward_dataset_prior(self):
        # 근거 0.5 vs 값 1.0, prior 0.7 → prior 근처로 수축 (0.714)
        sub = sub_scores(
            r01s=[1.0], rated_weights=[0.5],
            p_effs=[0.1], trust_values=[0.9], local_probs=[0.5], repeat_flags=[0.0],
            all_weights=[0.5], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=1, local_evidence=0.0,
        )
        self.assertAlmostEqual(sub.rating_adjusted, (0.5 + 7.0) / 10.5, places=3)
        self.assertLess(sub.rating_adjusted, 0.75)

    def test_rating_converges_with_evidence(self):
        # 근거 50이면 값 1.0에 수렴 ((50+7)/60 = 0.95)
        sub = sub_scores(
            r01s=[1.0], rated_weights=[50.0],
            p_effs=[0.1], trust_values=[0.9], local_probs=[0.5], repeat_flags=[0.0],
            all_weights=[50.0], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=30, local_evidence=0.0,
        )
        self.assertAlmostEqual(sub.rating_adjusted, 57.0 / 60.0, places=3)

    def test_food_none_without_evidence(self):
        sub = sub_scores(
            r01s=[1.0], rated_weights=[10.0],
            p_effs=[0.1], trust_values=[0.9], local_probs=[0.5], repeat_flags=[0.0],
            all_weights=[10.0], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=10, local_evidence=0.0,
        )
        self.assertIsNone(sub.food)
        self.assertIsNone(sub.value)

    def test_local_evidence_accumulates_weight(self):
        sub = sub_scores(
            r01s=[0.9, 0.9], rated_weights=[0.8, 0.8],
            p_effs=[0.1, 0.1], trust_values=[0.9, 0.9],
            local_probs=[0.8, 0.3], repeat_flags=[0.0, 0.0],
            all_weights=[0.8, 0.8], sentiments={"food": ([], []), "price": ([], [])},
            cfg=CFG, dataset_prior=0.7, n_raw=2, local_evidence=0.8,
        )
        self.assertAlmostEqual(sub.local_evidence, 0.8)


if __name__ == "__main__":
    unittest.main()
