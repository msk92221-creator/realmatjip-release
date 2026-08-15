import unittest

from app.config import ScoringConfig
from app.models import Restaurant
from app.scoring.engine import dataset_prior, rank_by, score_dataset

from .helpers import REFERENCE, make_analysis, make_restaurant, make_review

CFG = ScoringConfig()


class TestAdDownweighting(unittest.TestCase):
    def test_ad_inflated_rating_not_counted(self):
        """같은 평점 분포라도 광고 가능성이 높은 5점 리뷰는 평점을 끌어올리지 못한다."""
        restaurants = [make_restaurant("inflated", "광고부풀림"), make_restaurant("honest", "진짜혼합")]
        reviews = []
        # 두 식당 모두 4.0 리뷰 10개 + 5.0 리뷰 10개. 차이는 5점 리뷰의 광고 가능성.
        for i in range(10):
            reviews.append(make_review(f"i-low-{i}", rest="inflated", rating=4.0,
                                       analysis=make_analysis(ad=0.05)))
            reviews.append(make_review(f"i-high-{i}", rest="inflated", rating=5.0,
                                       analysis=make_analysis(ad=0.85, conf=0.9)))
            reviews.append(make_review(f"h-low-{i}", rest="honest", rating=4.0,
                                       analysis=make_analysis(ad=0.05)))
            reviews.append(make_review(f"h-high-{i}", rest="honest", rating=5.0,
                                       analysis=make_analysis(ad=0.05)))
        results = {r.restaurant.id: r for r in score_dataset(restaurants, reviews, CFG, REFERENCE)}

        inflated = results["inflated"]
        honest = results["honest"]
        # 단순 평균은 같지만(4.5★), 광고 5점의 영향력이 사라진 보정 평점은 낮아진다
        naive_inflated = sum(r.r01 for r in reviews if r.restaurant_id == "inflated") / 20
        naive_honest = sum(r.r01 for r in reviews if r.restaurant_id == "honest") / 20
        self.assertAlmostEqual(naive_inflated, naive_honest)
        self.assertLess(inflated.sub.rating_adjusted, honest.sub.rating_adjusted)
        self.assertLess(inflated.sub.rating_adjusted, naive_inflated - 0.03)
        self.assertLess(inflated.overall_a.score, honest.overall_a.score)
        self.assertLess(inflated.sub.trust, honest.sub.trust)

    def test_two_perfect_reviews_yield_no_score(self):
        restaurants = [make_restaurant("tiny", "리뷰2개집")]
        reviews = [
            make_review("t-1", rest="tiny", rating=5.0, analysis=make_analysis(ad=0.05)),
            make_review("t-2", rest="tiny", rating=5.0, analysis=make_analysis(ad=0.05)),
        ]
        result = score_dataset(restaurants, reviews, CFG, REFERENCE)[0]
        self.assertIsNone(result.overall_a.score)
        # 랭킹에서도 의미 있는 위치를 받지 않는다
        self.assertEqual(rank_by([result], "A")[0].restaurant.id, "tiny")


class TestSignalsEffect(unittest.TestCase):
    def test_repeat_visit_reviews_raise_repeat_score(self):
        restaurants = [make_restaurant("rep", "재방문집"), make_restaurant("norep", "일회성집")]
        reviews = []
        for i in range(8):
            reviews.append(make_review(f"r-{i}", rest="rep", rating=4.6,
                                       analysis=make_analysis(repeat=True)))
            reviews.append(make_review(f"n-{i}", rest="norep", rating=4.6,
                                       analysis=make_analysis(repeat=False)))
        results = {r.restaurant.id: r for r in score_dataset(restaurants, reviews, CFG, REFERENCE)}
        self.assertGreater(results["rep"].sub.repeat, results["norep"].sub.repeat)
        self.assertGreater(results["rep"].sub.repeat, 0.3)

    def test_multi_platform_consistency_beats_single(self):
        restaurants = [make_restaurant("multi", "멀티플랫폼"), make_restaurant("single", "단일플랫폼")]
        reviews = []
        sources = ["google_places", "naver_map", "kakao_map"]
        for i in range(9):
            reviews.append(make_review(f"m-{i}", rest="multi", source=sources[i % 3], rating=4.7))
            reviews.append(make_review(f"s-{i}", rest="single", source="google_places", rating=4.7))
        results = {r.restaurant.id: r for r in score_dataset(restaurants, reviews, CFG, REFERENCE)}
        self.assertGreater(results["multi"].consistency, results["single"].consistency)
        self.assertGreater(results["multi"].overall_a.score, results["single"].overall_a.score)


class TestMisc(unittest.TestCase):
    def test_pseudo_rating_used_when_rating_missing(self):
        restaurants = [make_restaurant("blog", "블로그집")]
        reviews = [
            make_review("b-1", rest="blog", rating=None,
                        analysis=make_analysis(pseudo=4.0, ad=0.3)),
            make_review("b-2", rest="blog", rating=None,
                        analysis=make_analysis(pseudo=4.0, ad=0.3)),
            make_review("b-3", rest="blog", rating=None,
                        analysis=make_analysis(pseudo=4.0, ad=0.3)),
        ]
        result = score_dataset(restaurants, reviews, CFG, REFERENCE)[0]
        # pseudo 4.0 → r01 0.75 근처의 보정 평점
        self.assertGreater(result.sub.rating_adjusted, 0.6)
        self.assertLess(result.sub.rating_adjusted, 0.85)

    def test_dataset_prior_defaults(self):
        self.assertEqual(dataset_prior([], CFG), CFG.default_dataset_prior)

    def test_local_badge_requires_evidence(self):
        restaurants = [make_restaurant("loc", "로컬집")]
        reviews = [
            make_review(f"l-{i}", rest="loc", analysis=make_analysis(local=0.85))
            for i in range(5)
        ]
        result = score_dataset(restaurants, reviews, CFG, REFERENCE)[0]
        self.assertTrue(result.local_badge)

        restaurants2 = [make_restaurant("noloc", "로컬아님")]
        reviews2 = [
            make_review(f"x-{i}", rest="noloc", analysis=make_analysis(local=0.2))
            for i in range(5)
        ]
        result2 = score_dataset(restaurants2, reviews2, CFG, REFERENCE)[0]
        self.assertFalse(result2.local_badge)


if __name__ == "__main__":
    unittest.main()
