"""Golden Set 불변식 테스트 — source-of-truth JSON 기준 (Phase 3A.2 §1).

각 리뷰는 정확히 하나의 ad_label을 가진다.
sum(ad_label counts) == total reviews.
manipulation_label은 별도 optional 축이다.
dataset(natural/challenge)은 ad_label과 독립적이다.
"""
import json
import unittest
from pathlib import Path

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "realdata" / "golden_set_labels.json"
IMPORT_PATH = Path(__file__).resolve().parent.parent / "realdata" / "import_phase3a.json"


class GoldenSetInvariantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        cls.import_data = json.loads(IMPORT_PATH.read_text(encoding="utf-8"))
        cls.all_reviews = [
            review
            for restaurant in cls.import_data["restaurants"]
            for review in restaurant["reviews"]
        ]

    def _match_label(self, text: str) -> dict:
        for rule in self.golden["labels"]:
            if rule["text_prefix"] in text:
                return rule
        return self.golden["_default"]

    def test_total_count_matches(self):
        """source-of-truth 라벨 수가 원본 리뷰 수와 일치해야 한다."""
        labeled = [self._match_label(r["text"]) for r in self.all_reviews]
        self.assertEqual(len(labeled), len(self.all_reviews))
        self.assertEqual(len(self.all_reviews), 59)

    def test_every_review_has_exactly_one_ad_label(self):
        """각 리뷰는 정확히 하나의 ad_label을 가진다."""
        valid_labels = {"ad", "likely_ad", "ambiguous", "normal"}
        for review in self.all_reviews:
            label = self._match_label(review["text"])["ad_label"]
            self.assertIn(label, valid_labels,
                         f"invalid ad_label '{label}' for: {review['text'][:30]}...")

    def test_ad_label_count_sum_equals_total(self):
        """sum(ad_label counts) == total reviews."""
        counts = {"ad": 0, "likely_ad": 0, "ambiguous": 0, "normal": 0}
        for review in self.all_reviews:
            counts[self._match_label(review["text"])["ad_label"]] += 1
        self.assertEqual(sum(counts.values()), 59,
                         f"sum={sum(counts.values())} != 59: {counts}")

    def test_expected_label_distribution(self):
        """재라벨링 기준에 따른 기대 분포: 4 likely_ad + 4 ambiguous + 51 normal = 59."""
        counts = {"ad": 0, "likely_ad": 0, "ambiguous": 0, "normal": 0}
        for review in self.all_reviews:
            counts[self._match_label(review["text"])["ad_label"]] += 1
        self.assertEqual(counts["likely_ad"], 4, f"likely_ad={counts['likely_ad']}, expected 4")
        self.assertEqual(counts["ambiguous"], 4, f"ambiguous={counts['ambiguous']}, expected 4")
        self.assertEqual(counts["normal"], 51, f"normal={counts['normal']}, expected 51")
        self.assertEqual(counts["ad"], 0, f"ad={counts['ad']}, expected 0 (명시적 협찬 없음)")

    def test_manipulation_label_is_optional_separate_axis(self):
        """manipulation_label은 별도 축이며 ad_label 총합에 포함하지 않는다."""
        manip_count = 0
        for review in self.all_reviews:
            rule = self._match_label(review["text"])
            if rule.get("manipulation_label"):
                manip_count += 1
                self.assertIn(rule["manipulation_label"], ("suspicious", "ambiguous", "normal"))
        # 성수 바이럴 3개만 suspicious
        self.assertEqual(manip_count, 3)

    def test_dataset_independent_of_ad_label(self):
        """dataset(natural/challenge)은 ad_label과 독립적 — 같은 ad_label이 양쪽에 있을 수 있다."""
        normal_natural = 0
        normal_challenge = 0
        for review in self.all_reviews:
            rule = self._match_label(review["text"])
            if rule["ad_label"] == "normal":
                if rule.get("dataset") == "challenge":
                    normal_challenge += 1
                else:
                    normal_natural += 1
        # 대부분의 normal은 natural에 있지만 일부는 challenge에 있을 수 있음
        self.assertGreater(normal_natural, 0)

    def test_blog_catalog_reviews_are_likely_ad(self):
        """카탈로그형 블로그 4개는 모두 likely_ad여야 한다."""
        catalog_prefixes = [
            "광화문 국밥 맛집으로 유명한 곳에",
            "서울 3대 국밥집 반열에 오른",
            "연남동 핫플레이스 수제돈까스",
            "강남 최고의 스테이크 하우스를",
        ]
        for prefix in catalog_prefixes:
            rule = self._match_label(prefix)
            self.assertEqual(rule["ad_label"], "likely_ad",
                           f"카탈로그 블로그 '{prefix[:20]}...'이(가) likely_ad가 아님")

    def test_viral_near_identical_are_ambiguous_and_suspicious(self):
        """성수 near-identical 3개는 ambiguous + suspicious여야 한다."""
        viral_prefixes = [
            "성수동 새로 생긴 카페 다녀왔어요. 분위기 진짜",
            "성수동 새로 생긴 카페 다녀왔어요. 분위기 너무",
            "성수동 새로 생긴 카페 다녀왔습니다. 분위기 진짜",
        ]
        for prefix in viral_prefixes:
            rule = self._match_label(prefix)
            self.assertEqual(rule["ad_label"], "ambiguous",
                           f"바이럴 '{prefix[:20]}...'이(가) ambiguous가 아님")
            self.assertEqual(rule.get("manipulation_label"), "suspicious")

    def test_sns_tourist_reviews_are_normal(self):
        """SNS 보고 방문한 일반 관광객 리뷰는 normal이어야 한다."""
        normal_sns = [
            "인스타에서 보고 왔는데 실물이",
            "요즘 SNS에서 제일 핫한",
            "릴스 보고 바로 왔어요",
            "SNS 보고 왔는데 실망했어요",
        ]
        for prefix in normal_sns:
            rule = self._match_label(prefix)
            self.assertEqual(rule["ad_label"], "normal",
                           f"SNS 반응 '{prefix[:20]}...'이(가) normal이 아님: {rule['ad_label']}")


if __name__ == "__main__":
    unittest.main()
