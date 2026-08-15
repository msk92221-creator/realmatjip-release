import unittest

from app.config import ScoringConfig
from app.scoring.duplicates import (
    char_ngrams,
    jaccard,
    mark_duplicates,
    near_duplicate_clusters,
    normalize_text,
)

from .helpers import make_review

CFG = ScoringConfig()

BASE = "성수동 새로 생긴 카페 다녀왔어요. 분위기 진짜 감성 최고고 파스터리도 맛있어요. 인생샷 건지기 딱 좋은 곳! 강추해요"


class TestNormalize(unittest.TestCase):
    def test_strips_punctuation_space_and_case(self):
        self.assertEqual(normalize_text("Hello, World!! 123"), "helloworld123")
        self.assertEqual(normalize_text("맛 있 어 요 !!"), "맛있어요")

    def test_ngrams(self):
        self.assertEqual(char_ngrams("abcd", 3), {"abc", "bcd"})


class TestNearDuplicateClusters(unittest.TestCase):
    def test_one_char_edit_clusters(self):
        reviews = [
            make_review("r-a", days=10, text=BASE),
            make_review("r-b", days=5, text=BASE.replace("진짜", "진쨰")),
            make_review("r-c", days=1, text=BASE.replace("강추해요", "강추해용")),
        ]
        clusters = near_duplicate_clusters(reviews, CFG)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 3)

    def test_different_texts_do_not_cluster(self):
        reviews = [
            make_review("r-a", days=10, text="회사가 근처라 점심으로 자주 가는 곳. 국물 맛이 항상 일정해서 좋아요."),
            make_review("r-b", days=5, text="주말에 가족과 방문. 갈비찜은 부드럽고 양도 넉넉했어요. 직원이 친절해요."),
        ]
        self.assertEqual(near_duplicate_clusters(reviews, CFG), [])

    def test_short_common_phrases_excluded(self):
        reviews = [
            make_review("r-a", days=10, text="맛있어요"),
            make_review("r-b", days=5, text="맛있어요"),
        ]
        self.assertEqual(near_duplicate_clusters(reviews, CFG), [])

    def test_fixture_viral_dup_family_clusters(self):
        from fixtures.templates import TEMPLATES

        reviews = [
            make_review(f"r-{i}", days=3 + i, text=text)
            for i, text in enumerate(TEMPLATES["viral_dup"])
        ]
        marked = mark_duplicates(reviews, CFG)
        # 10개 중 대표 1개를 제외한 대부분이 멤버로 표시된다
        self.assertGreaterEqual(len(marked), 8)
        self.assertLessEqual(len(marked), 9)

    def test_representative_is_earliest(self):
        reviews = [
            make_review("r-new", days=1, text=BASE),
            make_review("r-old", days=30, text=BASE.replace("감성", "감셩")),
        ]
        marked = mark_duplicates(reviews, CFG)
        self.assertEqual(marked, {"r-new": "r-old"})


if __name__ == "__main__":
    unittest.main()
