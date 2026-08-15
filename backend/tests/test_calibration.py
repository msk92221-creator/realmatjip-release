"""Calibration(2축 분리 + Natural/Challenge) 계산 테스트."""
import os
import tempfile
import unittest
from datetime import datetime

from app.db.database import init_db, make_engine, make_session_factory
from app.db.mappers import analysis_to_row, restaurant_to_row, review_to_row
from app.db.models import ManualLabelORM
from app.models import Restaurant, Review
from app.analysis import ReviewAnalysis
from app.pipeline.calibration import calibration_report


def make_analysis(ad_probability: float) -> ReviewAnalysis:
    return ReviewAnalysis(
        analyzer="fake", prompt_version="v1",
        ad_probability=ad_probability, ad_confidence=0.9,
        authenticity=0.8, specificity=0.8, local_probability=0.5,
        sentiment={}, visit_context={}, summary="",
    )


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        url = "sqlite:///" + os.path.join(self.tmp.name, "cal.db").replace("\\", "/")
        self.engine = make_engine(url)
        init_db(self.engine)
        self.sf = make_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _seed(self, cases):
        """cases: [(review_id, ad_label, ad_probability, dataset, manipulation_label)]"""
        with self.sf() as session:
            session.merge(restaurant_to_row(Restaurant("a", "A", "한식", 1, 2)))
            for rid, ad_label, p, dataset, manip in cases:
                review = Review(id=rid, restaurant_id="a", source="naver_map",
                                rating=4.0, text=f"리뷰 {rid}", reviewed_at=datetime(2026, 8, 1))
                session.merge(review_to_row(review))
                session.merge(analysis_to_row(rid, make_analysis(p)))
                session.merge(ManualLabelORM(
                    review_id=rid, ad_label=ad_label,
                    manipulation_label=manip, dataset=dataset,
                ))
            session.commit()

    def _report(self):
        with self.sf() as session:
            return calibration_report(session, ad_threshold=0.7)

    def test_perfect_prediction(self):
        self._seed([
            ("r1", "ad", 0.9, "challenge", None),
            ("r2", "normal", 0.1, "natural", None),
            ("r3", "ad", 0.8, "challenge", None),
            ("r4", "normal", 0.2, "natural", None),
        ])
        report = self._report()
        ad_all = report["ad_axis"]["all"]
        self.assertEqual(ad_all["n_scored"], 4)
        self.assertEqual(ad_all["tp"], 2)
        self.assertEqual(ad_all["tn"], 2)
        self.assertEqual(ad_all["precision"], 1.0)
        self.assertEqual(ad_all["f1"], 1.0)

    def test_fp_fn_classification(self):
        self._seed([
            ("r1", "normal", 0.9, "natural", None),   # FP
            ("r2", "ad", 0.1, "challenge", None),     # FN
            ("r3", "ad", 0.8, "challenge", None),     # TP
            ("r4", "normal", 0.2, "natural", None),   # TN
        ])
        report = self._report()
        ad_all = report["ad_axis"]["all"]
        self.assertEqual(ad_all["fp"], 1)
        self.assertEqual(ad_all["fn"], 1)
        self.assertEqual(ad_all["precision"], 0.5)
        self.assertEqual(ad_all["recall"], 0.5)
        self.assertEqual(len(ad_all["fp_examples"]), 1)
        self.assertEqual(ad_all["fp_examples"][0]["review_id"], "r1")

    def test_natural_vs_challenge_separated(self):
        self._seed([
            ("r1", "normal", 0.9, "natural", None),   # FP (natural)
            ("r2", "normal", 0.8, "challenge", None), # FP (challenge)
            ("r3", "ad", 0.9, "challenge", None),     # TP (challenge)
            ("r4", "normal", 0.1, "natural", None),   # TN (natural)
        ])
        report = self._report()
        natural = report["ad_axis"]["natural"]
        challenge = report["ad_axis"]["challenge"]
        # Natural에는 FP 1건, Challenge에는 FP 1건 + TP 1건
        self.assertEqual(natural["fp"], 1)
        self.assertEqual(natural["n_scored"], 2)
        self.assertEqual(challenge["fp"], 1)
        self.assertEqual(challenge["tp"], 1)
        self.assertEqual(challenge["n_scored"], 2)

    def test_ambiguous_excluded(self):
        self._seed([
            ("r1", "ambiguous", 0.95, "challenge", None),
            ("r2", "normal", 0.1, "natural", None),
        ])
        report = self._report()
        self.assertEqual(report["ad_axis"]["all"]["n_scored"], 1)
        self.assertEqual(report["ad_axis"]["all"]["tn"], 1)

    def test_likely_ad_is_positive(self):
        self._seed([
            ("r1", "likely_ad", 0.75, "challenge", None),
            ("r2", "normal", 0.3, "natural", None),
        ])
        report = self._report()
        self.assertEqual(report["ad_axis"]["all"]["tp"], 1)

    def test_manipulation_label_independent(self):
        """manipulation_label은 ad 계산에 영향을 주지 않는다 (Phase 3A.1 분리 원칙)."""
        self._seed([
            ("r1", "normal", 0.1, "natural", "suspicious"),  # 조작 의심이지만 광고는 아님
            ("r2", "ad", 0.9, "challenge", "normal"),         # 광고지만 조작은 아님
        ])
        report = self._report()
        ad = report["ad_axis"]["all"]
        self.assertEqual(ad["tn"], 1)   # r1: normal → TN
        self.assertEqual(ad["tp"], 1)   # r2: ad → TP
        # manipulation_label "suspicious"이 ad 계산에 영향 없음 확인


if __name__ == "__main__":
    unittest.main()
