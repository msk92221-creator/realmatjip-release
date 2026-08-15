import unittest

from app.config import ALGORITHM_VERSION, ScoringConfig, observed_ad_prior


class TestAlgorithmVersion(unittest.TestCase):
    def test_version_stamp(self):
        """결정 #6: 알고리즘 버전은 config에 명시된다."""
        self.assertEqual(ScoringConfig().algorithm_version, "v0.1-phase0")
        self.assertEqual(ALGORITHM_VERSION, "v0.1-phase0")


class TestEvidenceLabel(unittest.TestCase):
    def test_labels(self):
        cfg = ScoringConfig()
        self.assertEqual(cfg.evidence_label(0.80), "높음")
        self.assertEqual(cfg.evidence_label(0.50), "보통")
        self.assertEqual(cfg.evidence_label(0.20), "낮음")


class TestObservedPrior(unittest.TestCase):
    def test_few_labels_returns_none(self):
        labels = ["ad"] * 10 + ["normal"] * 10
        self.assertIsNone(observed_ad_prior(labels, ScoringConfig()))

    def test_enough_labels_returns_mean(self):
        labels = ["ad"] * 15 + ["normal"] * 15  # 0.95×15 + 0.05×15의 평균
        expected = (0.95 * 15 + 0.05 * 15) / 30
        self.assertAlmostEqual(observed_ad_prior(labels, ScoringConfig()), expected)

    def test_ignores_unknown_and_none(self):
        labels = ["ad"] * 29 + ["normal"] + [None, "weird"]
        # None/알 수 없는 라벨은 무시되고, 30개 라벨의 평균이 된다
        self.assertAlmostEqual(observed_ad_prior(labels, ScoringConfig()), (0.95 * 29 + 0.05) / 30)

    def test_threshold_is_configurable(self):
        cfg = ScoringConfig(min_labeled_for_observed_prior=3)
        self.assertAlmostEqual(observed_ad_prior(["ad", "ad", "ad"], cfg), 0.95)


class TestOverallWeights(unittest.TestCase):
    def test_version_b_reduces_rating_share(self):
        cfg = ScoringConfig()
        self.assertLess(
            cfg.overall_weights["B"]["rating"], cfg.overall_weights["A"]["rating"]
        )

    def test_gains_sum_to_100(self):
        cfg = ScoringConfig()
        for version, weights in cfg.overall_weights.items():
            self.assertAlmostEqual(sum(weights.values()), 100.0, msg=version)
