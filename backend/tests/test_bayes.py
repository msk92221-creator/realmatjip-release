import unittest

from app.scoring.bayes import shrunk_mean


class TestShrunkMean(unittest.TestCase):
    def test_zero_weight_returns_prior(self):
        self.assertEqual(shrunk_mean([1.0, 0.0], [0.0, 0.0], prior=0.7, c=10.0), 0.7)

    def test_heavy_weight_converges_to_weighted_mean(self):
        result = shrunk_mean([1.0, 0.0], [1000.0, 1000.0], prior=0.0, c=1.0)
        self.assertAlmostEqual(result, 0.5, places=3)

    def test_mixture_between_prior_and_mean(self):
        # 값 1.0 (w=10), prior 0.0, C=10 → 정확히 중간
        self.assertAlmostEqual(shrunk_mean([1.0], [10.0], prior=0.0, c=10.0), 0.5)

    def test_weighted_by_review_weight(self):
        # 리뷰 A(w=3, v=1.0), 리뷰 B(w=1, v=0.0), prior 0.5, C=0 → 0.75
        self.assertAlmostEqual(shrunk_mean([1.0, 0.0], [3.0, 1.0], prior=0.5, c=0.0), 0.75)
